import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'd6f7be1f6d717e7b01c27836e5eeede07032bafca9ac23b9beab4adc70fe8f82')
    DEBUG = True
    # 5 evidencias x 10 MB + margen del formulario (igual que el backend)
    MAX_CONTENT_LENGTH = 56 * 1024 * 1024
