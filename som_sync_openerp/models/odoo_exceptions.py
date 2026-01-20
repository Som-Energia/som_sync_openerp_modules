# -*- coding: utf-8 -*-


class CreationNotSupportedException(Exception):
    """Creation operation not suppported in Odoo API for this model"""

    def __init__(self, msg):
        super(CreationNotSupportedException, self).__init__(msg)
        self.msg = "Odoo no permet la creació de models {}".format(msg)

    def __repr__(self):
        return self.msg

    def __str__(self):
        return self.__repr__()


class ERPObjectNotExistsException(Exception):
    """Creation operation not suppported in Odoo API for this model"""

    def __init__(self, msg):
        super(ERPObjectNotExistsException, self).__init__(msg)
        self.msg = "L'ojecte ERP a sincronitzar amb Odoo no existeix: {}".format(msg)

    def __repr__(self):
        return self.msg

    def __str__(self):
        return self.__repr__()


class UpdateNotSupportedException(Exception):
    """Update operation not supported in Odoo API for this model"""

    def __init__(self, msg):
        super(UpdateNotSupportedException, self).__init__(msg)
        self.msg = "Odoo no permet l'actualització de models {}".format(msg)

    def __repr__(self):
        return self.msg

    def __str__(self):
        return self.__repr__()


class ForeingKeyNotAvailable(Exception):
    """Foreign Key required for operation is not available in Odoo API for this model"""

    def __init__(self, msg):
        super(ForeingKeyNotAvailable, self).__init__(msg)
        self.msg = "Odoo no ha permés la creació o obtenció de la FK: {}".format(msg)

    def __repr__(self):
        return self.msg

    def __str__(self):
        return self.__repr__()
