from PyQt5.QtCore import QPoint, QSettings

class AliceSettings():
    ORG_NAME = "Alice Converter"
    APP_NAME = "Alice"
    QSETTINGS_KEY = "settings"

    MIN_FREQ = 30.0
    MAX_FREQ = 50.0

    def __init__(self, window_position = QPoint(200, 200), input_folder=None, output_folder=None, noise=True, compressor=True, frequency=40.0, save_as_60_min_chunks=True):
        self.window_position = window_position

        self.input_folder = input_folder
        self.output_folder = output_folder

        self.noise = noise
        self.compressor = compressor
        self.frequency = max(min(frequency, self.MAX_FREQ), self.MIN_FREQ)

        self.save_as_60_min_chunks = save_as_60_min_chunks

    def _to_diccy(self):
        return self.__dict__

    def copy(self):
        return AliceSettings(**self._to_diccy())
    
    def save(self):
        try:
            qsett = QSettings(self.ORG_NAME, self.APP_NAME)
            qsett.setValue(self.QSETTINGS_KEY, self._to_diccy())
        except Exception:
            pass

    @classmethod 
    def load(cls):
        diccy = None
        try:
            qsett = QSettings(cls.ORG_NAME, cls.APP_NAME)
            diccy = qsett.value(cls.QSETTINGS_KEY, None)
        except Exception:
            print("Failed to load settings.")
        
        if diccy is None:
            return cls()
        return cls(**diccy)
