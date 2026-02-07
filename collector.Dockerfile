FROM python:3.11-slim

# Install RTL-SDR and multimon-ng for FLEX protocol decoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    rtl-sdr multimon-ng libusb-1.0-0 && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir requests

WORKDIR /collector

COPY scripts/collector.py .

ENV SAGRN_SERVER_URL=http://backend:8000
ENV COLLECTOR_ID=pager1
ENV PAGER_FREQUENCY=148.8125M
ENV SAGRN_LOG_DIR=/collector/logs

CMD ["python3", "collector.py"]
