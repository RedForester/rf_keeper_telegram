import logging

logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(name)s %(levelname)s: %(message)s')

logger = logging.getLogger('bot')
logger.setLevel(logging.INFO)

logger.info('Logging is enabled')
