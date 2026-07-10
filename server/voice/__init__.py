import logging

log = logging.getLogger("dexter.voice")

from voice.pipeline import VoicePipeline, create_pipeline
from voice.ws_handler import router as voice_router

log.info("Voice module loaded")
