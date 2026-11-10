# Step 5: the cached version. Slow, rarely-changing steps come first.
# Start from the official Python 3.12 image. "slim" is the small version.
FROM python:3.12-slim
# Make /app the working folder inside the container (created if it is missing).
WORKDIR /app
# Copy ONLY the dependency list first. Docker reuses (caches) this step
# until requirements.txt changes.
COPY requirements.txt .
# Install the requirements. --no-cache-dir stops pip keeping a download cache,
# which keeps the image smaller.
RUN pip install --no-cache-dir -r requirements.txt
# Now copy the rest of the project. Code changes often, so this comes last.
COPY . .
# When the container starts, run: python app.py
CMD ["python", "app.py"]
