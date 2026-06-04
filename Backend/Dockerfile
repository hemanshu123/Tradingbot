FROM python:3.14

# Install .NET 8.0 SDK
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates && \
    wget https://dot.net/v1/dotnet-install.sh -O dotnet-install.sh && \
    chmod +x dotnet-install.sh && \
    ./dotnet-install.sh --version 8.0 --install-dir /usr/local/dotnet && \
    ln -s /usr/local/dotnet/dotnet /usr/local/bin/dotnet && \
    rm dotnet-install.sh && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install -r requirements.txt

# Copy app code
COPY . .

# Run the app
CMD ["python", "server.py"]