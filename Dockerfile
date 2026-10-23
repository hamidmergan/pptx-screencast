FROM python:3.12-slim

# LibreOffice renders the slides, poppler turns the PDF into pictures,
# ffmpeg builds the video. The fonts keep the slides from being rendered
# with substitutes everywhere. git lets pip fetch the sibling tool doc2speech,
# which is named with its repository in pyproject.toml.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-impress \
        poppler-utils \
        ffmpeg \
        fontconfig \
        fonts-dejavu \
        fonts-liberation \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir ".[ui]" \
    && useradd --create-home --uid 1000 app

USER app
EXPOSE 8000

# Settings come from PPTX_SCREENCAST_* environment variables, for example
# PPTX_SCREENCAST_BASE_URL, PPTX_SCREENCAST_MODEL and PPTX_SCREENCAST_TTS_MODEL.
CMD ["pptx-screencast", "serve", "--host", "0.0.0.0", "--port", "8000"]
