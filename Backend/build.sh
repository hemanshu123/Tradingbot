#!/bin/bash
echo "[BUILD] Installing .NET 8.0..."

# Download and install .NET 8.0 SDK
curl -fsSL https://dot.net/v1/dotnet-install.sh -o dotnet-install.sh
chmod +x dotnet-install.sh
./dotnet-install.sh --version 8.0 --install-dir ./dotnet

# Add to PATH
export PATH="$(pwd)/dotnet:$PATH"

echo "[BUILD] Verifying .NET installation..."
./dotnet/dotnet --version

echo "[BUILD] Installing Python dependencies..."
pip install -r requirements.txt

echo "[BUILD] Build complete!"