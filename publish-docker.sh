#!/bin/bash

# Publish AI Assistant API to Docker Hub
set -e

# Configuration
DOCKERHUB_USERNAME="foxelvoret"
IMAGE_NAME="ai-assistant"
IMAGE_TAG="latest"
FULL_IMAGE="${DOCKERHUB_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "🐳 Publishing AI Assistant API to Docker Hub"
echo "=========================================="

# Step 1: Check if logged in to Docker Hub
echo "🔐 Checking Docker Hub login..."
if ! docker info | grep -q "Username"; then
    echo "❌ Not logged in to Docker Hub. Please run: docker login"
    exit 1
fi

echo "✅ Logged in to Docker Hub as $(docker info | grep Username | awk '{print $2}')"

# Step 2: Navigate to code directory
echo "📁 Navigating to code directory..."
cd "$(dirname "$0")/code"

# Step 3: Build the Docker image
echo "🔨 Building Docker image: ${FULL_IMAGE}"
docker build -t ${FULL_IMAGE} .

# Step 4: Test the image (optional)
echo "🧪 Testing Docker image..."
if docker run --rm -d -p 8000:8000 --name test-api ${FULL_IMAGE}; then
    echo "✅ Container started successfully"
    
    # Wait for container to start
    sleep 5
    
    # Test health endpoint
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Health check passed"
    else
        echo "⚠️  Health check failed, but continuing..."
    fi
    
    # Stop test container
    docker stop test-api
else
    echo "⚠️  Container test failed, but continuing..."
fi

# Step 5: Push to Docker Hub
echo "📤 Pushing to Docker Hub..."
docker push ${FULL_IMAGE}

# Step 6: Verify
echo "🔍 Verifying image on Docker Hub..."
if docker pull ${FULL_IMAGE} > /dev/null 2>&1; then
    echo "✅ Image successfully published to Docker Hub!"
    echo "🌐 Repository: https://hub.docker.com/r/${DOCKERHUB_USERNAME}/${IMAGE_NAME}"
    echo "📋 Image: ${FULL_IMAGE}"
else
    echo "❌ Failed to verify image on Docker Hub"
    exit 1
fi

echo ""
echo "🚀 Ready for deployment!"
echo "💡 Use this image in your Helm chart:"
echo "   api.image.repository: ${DOCKERHUB_USERNAME}/${IMAGE_NAME}"
echo "   api.image.tag: ${IMAGE_TAG}"
