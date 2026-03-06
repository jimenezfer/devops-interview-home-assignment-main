from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import asyncpg
import redis.asyncio as redis
import json
import os
import asyncio
import httpx
import hashlib
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from datetime import datetime
import time
import uuid

# Load environment variables from .env file
load_dotenv()

# Configure logging for AWS EKS deployment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS Infrastructure Configuration
COMPANY_NAME = os.getenv("COMPANY_NAME", "AI Assistant API")
VLLM_HOST = os.getenv("VLLM_HOST", "smol-lm2-service")
VLLM_PORT = os.getenv("VLLM_PORT", "8000")
VLLM_URL = f"http://{VLLM_HOST}:{VLLM_PORT}/v1/chat/completions"
MODEL_NAME = "SmolLM2-135M-Instruct"


# Aurora PostgreSQL and ElastiCache Redis connections
db_pool = None
redis_client = None
http_client = None

CACHE_TTL = 3600  # 1 hour for ElastiCache


def serialize_record(record):
    """Convert Aurora PostgreSQL record to JSON-serializable dict"""
    if record is None:
        return None
    
    result = dict(record)
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    return result

def hash_question(question: str) -> str:
    """Generate SHA-256 hash for question caching"""
    return hashlib.sha256(question.encode()).hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Initialize AWS services connections
    global db_pool, redis_client, http_client
    
    logger.info("Initializing Aurora PostgreSQL connection...")
    db_pool = await _wait_for_postgres()
    
    logger.info("Initializing ElastiCache Redis connection...")
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True
    )
    
    logger.info("Initializing HTTP client for vLLM service...")
    http_client = httpx.AsyncClient(timeout=30.0)
    
    logger.info("AI Assistant API ready on EKS with Aurora, ElastiCache, and vLLM")
    yield
    
    # Shutdown
    logger.info("Shutting down connections...")
    await db_pool.close()
    await redis_client.close()
    await http_client.aclose()

app = FastAPI(
    title=f"{COMPANY_NAME}",
    description="AI-powered question answering API deployed on EKS with Aurora PostgreSQL, ElastiCache Redis, and SmolLM2-135M-Instruct",
    version="1.0.0",
    lifespan=lifespan
)


# Pydantic Models for AI Question Answering
class QuestionRequest(BaseModel):
    question: str
    session_id: str | None = None

class QuestionResponse(BaseModel):
    question: str
    answer: str
    model: str
    response_time_ms: int
    cached: bool = False
    session_id: str | None = None

class HealthResponse(BaseModel):
    status: str
    aurora: str
    elasticache: str
    vllm_service: str
    timestamp: str


# Aurora PostgreSQL connection with retry logic
async def _wait_for_postgres(max_attempts=30, delay=2):
    """Wait for Aurora PostgreSQL to be ready"""
    for attempt in range(max_attempts):
        try:
            pool = await asyncpg.create_pool(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                database=os.getenv("POSTGRES_DB", "ai_assistant"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres"),
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info(f"Connected to Aurora PostgreSQL on attempt {attempt + 1}")
            return pool
        except (ConnectionRefusedError, asyncpg.PostgresConnectionError, OSError) as e:
            if attempt == max_attempts - 1:
                logger.error(f"Failed to connect to Aurora after {max_attempts} attempts: {e}")
                raise
            logger.warning(f"Aurora connection attempt {attempt + 1} failed, retrying in {delay}s...")
            await asyncio.sleep(delay)


@app.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest, http_request: Request):
    """
    Accept a question and return AI-generated answer from SmolLM2-135M-Instruct via vLLM
    Uses ElastiCache for caching and Aurora for persistent storage
    """
    start_time = time.time()
    
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    # Generate or use provided session ID
    session_id = request.session_id or str(uuid.uuid4())
    question_hash = hash_question(request.question.strip())
    
    logger.info(f"Processing question for session {session_id}: {request.question[:100]}...")
    
    try:
        # Check ElastiCache first
        cache_key = f"question:{question_hash}"
        cached_response = await redis_client.get(cache_key)
        
        if cached_response:
            cached_data = json.loads(cached_response)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Update cache hit count in Aurora
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE question_cache SET hit_count = hit_count + 1, last_accessed = CURRENT_TIMESTAMP WHERE question_hash = $1",
                    question_hash
                )
            
            logger.info(f"Cache hit for question hash {question_hash}")
            
            return QuestionResponse(
                question=request.question,
                answer=cached_data["answer"],
                model=cached_data["model"],
                response_time_ms=response_time_ms,
                cached=True,
                session_id=session_id
            )
        
        # Not cached - query vLLM service
        vllm_payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": request.question}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        
        logger.info(f"Querying vLLM service at {VLLM_URL}")
        
        response = await http_client.post(
            VLLM_URL,
            json=vllm_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            logger.error(f"vLLM returned status {response.status_code}: {response.text}")
            await _log_api_metrics("/ask", response.status_code, int((time.time() - start_time) * 1000), http_request.headers.get("user-agent"))
            raise HTTPException(
                status_code=503,
                detail=f"AI service unavailable (status: {response.status_code})"
            )
        
        vllm_response = response.json()
        
        if "choices" not in vllm_response or not vllm_response["choices"]:
            logger.error(f"Invalid vLLM response format: {vllm_response}")
            raise HTTPException(status_code=502, detail="Invalid response from AI service")
        
        answer = vllm_response["choices"][0]["message"]["content"].strip()
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Store in Aurora PostgreSQL
        async with db_pool.acquire() as conn:
            # Store in question history
            await conn.execute(
                "INSERT INTO question_history (question, answer, model, response_time_ms, user_session_id) VALUES ($1, $2, $3, $4, $5)",
                request.question, answer, MODEL_NAME, response_time_ms, session_id
            )
            
            # Store in question cache for future requests
            await conn.execute(
                "INSERT INTO question_cache (question_hash, question, answer, model) VALUES ($1, $2, $3, $4) ON CONFLICT (question_hash) DO NOTHING",
                question_hash, request.question, answer, MODEL_NAME
            )
        
        # Cache in ElastiCache Redis
        cache_data = {
            "answer": answer,
            "model": MODEL_NAME,
            "timestamp": datetime.utcnow().isoformat()
        }
        await redis_client.setex(cache_key, CACHE_TTL, json.dumps(cache_data))
        
        logger.info(f"Generated answer in {response_time_ms}ms using {MODEL_NAME}")
        
        await _log_api_metrics("/ask", 200, response_time_ms, http_request.headers.get("user-agent"))
        
        return QuestionResponse(
            question=request.question,
            answer=answer,
            model=MODEL_NAME,
            response_time_ms=response_time_ms,
            cached=False,
            session_id=session_id
        )
        
    except httpx.TimeoutException:
        logger.error("Request to vLLM timed out")
        await _log_api_metrics("/ask", 504, int((time.time() - start_time) * 1000), http_request.headers.get("user-agent"))
        raise HTTPException(status_code=504, detail="AI service request timed out")
    
    except httpx.ConnectError:
        logger.error(f"Failed to connect to vLLM at {VLLM_URL}")
        await _log_api_metrics("/ask", 503, int((time.time() - start_time) * 1000), http_request.headers.get("user-agent"))
        raise HTTPException(status_code=503, detail="AI service unavailable - connection failed")
    
    except Exception as e:
        logger.error(f"Unexpected error processing question: {str(e)}")
        await _log_api_metrics("/ask", 500, int((time.time() - start_time) * 1000), http_request.headers.get("user-agent"))
        raise HTTPException(status_code=500, detail="Internal server error")

async def _log_api_metrics(endpoint: str, status_code: int, response_time_ms: int, user_agent: str = None):
    """Log API metrics to Aurora PostgreSQL for monitoring"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO api_metrics (endpoint, response_time_ms, status_code, user_agent) VALUES ($1, $2, $3, $4)",
                endpoint, response_time_ms, status_code, user_agent
            )
    except Exception as e:
        logger.error(f"Failed to log API metrics: {e}")







@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Comprehensive health check for AWS infrastructure components
    """
    health_status = {
        "status": "healthy",
        "aurora": "unknown",
        "elasticache": "unknown",
        "vllm_service": "unknown",
        "timestamp": None
    }
    
    # Check Aurora PostgreSQL
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        health_status["aurora"] = "healthy"
        logger.info("Aurora PostgreSQL health check passed")
    except Exception as e:
        health_status["aurora"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
        logger.error(f"Aurora health check failed: {e}")
    
    # Check ElastiCache Redis
    try:
        await redis_client.ping()
        health_status["elasticache"] = "healthy"
        logger.info("ElastiCache Redis health check passed")
    except Exception as e:
        health_status["elasticache"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
        logger.error(f"ElastiCache health check failed: {e}")
    
    # Check vLLM service
    try:
        response = await http_client.get(f"http://{VLLM_HOST}:{VLLM_PORT}/health", timeout=5.0)
        if response.status_code == 200:
            health_status["vllm_service"] = "healthy"
            logger.info("vLLM service health check passed")
        else:
            health_status["vllm_service"] = f"unhealthy (status: {response.status_code})"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["vllm_service"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
        logger.error(f"vLLM health check failed: {e}")
    
    health_status["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    return health_status

@app.get("/")
async def root():
    """
    Root endpoint - redirect to chatbox
    """
    return RedirectResponse(url="/chatbox")

@app.get("/chatbox")
async def chatbox_ui():
    """
    Serve the AI chatbox UI
    """
    chatbox_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Chat</title>
        <style>
            body { font: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
            .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .header { background: #007bff; color: white; padding: 15px; border-radius: 8px 8px 0 0; text-align: center; }
            .messages { height: 400px; overflow-y: auto; padding: 20px; border-bottom: 1px solid #eee; }
            .message { margin-bottom: 15px; display: flex; }
            .user { justify-content: flex-end; }
            .ai { justify-content: flex-start; }
            .bubble { max-width: 70%; padding: 10px 15px; border-radius: 15px; }
            .user .bubble { background: #007bff; color: white; }
            .ai .bubble { background: #e9ecef; color: #333; }
            .input { padding: 20px; display: flex; }
            .input input { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 20px; outline: none; }
            .input button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 20px; margin-left: 10px; cursor: pointer; }
            .loading { text-align: center; padding: 10px; color: #666; font-style: italic; }
            .error { background: #f8d7da; color: #721c24; padding: 10px; margin: 10px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">🤖 AI Assistant</div>
            <div class="messages" id="messages">
                <div class="message ai">
                    <div class="bubble">Hello! How can I help you?</div>
                </div>
            </div>
            <div class="loading" id="loading" style="display:none;">Thinking...</div>
            <div class="input">
                <form id="form">
                    <input type="text" id="msg" placeholder="Ask anything..." required>
                    <button type="submit">Send</button>
                </form>
            </div>
        </div>
        <script>
            const messages = document.getElementById('messages');
            const input = document.getElementById('msg');
            const loading = document.getElementById('loading');
            
            function addMessage(text, isUser) {
                const div = document.createElement('div');
                div.className = `message ${isUser ? 'user' : 'ai'}`;
                div.innerHTML = `<div class="bubble">${text}</div>`;
                messages.appendChild(div);
                messages.scrollTop = messages.scrollHeight;
            }
            
            async function send() {
                const text = input.value.trim();
                if (!text) return;
                
                addMessage(text, true);
                input.value = '';
                loading.style.display = 'block';
                
                try {
                    const r = await fetch('/ask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({question: text})
                    });
                    
                    if (!r.ok) throw new Error('API error');
                    
                    const data = await r.json();
                    addMessage(data.answer || 'Sorry, I cannot help with that.', false);
                } catch (e) {
                    addMessage('Error: ' + e.message, false);
                } finally {
                    loading.style.display = 'none';
                }
            }
            
            document.getElementById('form').onsubmit = e => { e.preventDefault(); send(); };
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=chatbox_html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Run with: uvicorn main:app --host 0.0.0.0 --port 8000