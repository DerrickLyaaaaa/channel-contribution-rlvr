FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY rlvr_business ./rlvr_business
COPY examples ./examples
COPY tests ./tests
RUN python -m unittest discover -s tests -v
USER 65532:65532
CMD ["python", "-m", "examples.demo"]
