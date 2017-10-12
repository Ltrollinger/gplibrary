" cap spar "
from gpkit import Model, Variable, Vectorize
from chord_spar_loading import ChordSparL
from gustloading import GustL

class CapSpar(Model):
    "cap spar model"
    def setup(self, N):

        # phyiscal properties
        rhocfrp = Variable("\\rho_{CFRP}", 1.6, "g/cm^3", "density of CFRP")
        E = Variable("E", 2e7, "psi", "Youngs modulus of CFRP")

        with Vectorize(N-1):
            hin = Variable("h_{in}", "in", "inner spar height")
            I = Variable("I", "m^4", "spar x moment of inertia")
            Sy = Variable("S_y", "m**3", "section modulus")
            dm = Variable("dm", "kg", "segment spar mass")
            dmdy = Variable("(dm/dy)", "kg/m", "spar mass per length")
            w = Variable("w", "in", "spar width")
            t = Variable("t", "in", "spar cap thickness")
            tshear = Variable("t_{shear}", "in", "shear web thickness")

        W = Variable("W", "lbf", "spar weight")
        w_lim = Variable("w_{lim}", 0.15, "-", "spar width to chord ratio")
        tshearmin = Variable("t_{shear-min}", 0.012, "in",
                             "min shear web thickness")
        g = Variable("g", 9.81, "m/s^2", "gravitational acceleration")
        mfac = Variable("m_{fac}", 0.97, "-", "curvature knockdown factor")
        rhofoam = Variable("\\rho_{foam}", 0.036, "g/cm^3", "foam density")

        constraints = [I/mfac <= 2*w*t*(hin/2)**2,
                       dmdy >= (rhocfrp*(2*w*t + 2*tshear*(w + hin + 2*t))
                                + rhofoam*w*hin),
                       W >= 2*dm.sum()*g,
                       Sy*(hin/2 + t) <= I,
                       tshear >= tshearmin
                      ]

        self.loading = ChordSparL
        self.gustloading = GustL

        return constraints