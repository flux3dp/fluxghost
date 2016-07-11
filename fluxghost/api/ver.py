
import fluxclient
import fluxghost


def ver_api_mixin(cls):
    class VerApi(cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.send_json(fluxclient=fluxclient.__version__,
                           fluxghost=fluxghost.__version__)
            self.close()
    return VerApi
