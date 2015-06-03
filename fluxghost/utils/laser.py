class laser(object):
    """base class for all laser usage calss"""
    def __init__(self):
        pass

    def turnOn(self):
        global laser_on
        laser_on = True
        return ["G4 P1", "@X9L0"]

    def turnOff(self):
        global laser_on
        laser_on = False
        return ["G4 P1", "@X9L255"]

    def turnHalf(self):
        global laser_on
        laser_on = False
        return ["G4 P1", "@X9L220"]
