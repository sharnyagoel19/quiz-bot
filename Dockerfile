# Use the official Playwright Python image so browsers work out of the box
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to cache dependencies
COPY requirements.txt .

# Install Python libraries
RUN pip install --no-cache-dir -r requirements.txt

# Install the Chromium browser explicitly
RUN playwright install chromium

# Copy the rest of your application code
COPY . .

# Expose port 8000 for the world to access
EXPOSE 8000

# Start the server using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
