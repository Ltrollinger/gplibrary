from numpy import pi
import matplotlib.pyplot as plt
from gpkit import VectorVariable, Variable, Model, units
from gpkit.tools import te_exp_minus1
import gpkit
import numpy as np
gpkit.settings['latex_modelname'] = False

class GasPoweredHALE(Model):
    def setup(self):

        # define number of segments
        NSeg = 9 # number of flight segments
        NCruise = 2 # number of cruise segments
        NClimb = 2 # number of climb segments
        NLoiter = NSeg - NCruise - NClimb# number of loiter segments
        iCruise = [1, -1] # cuise index
        iLoiter = [3] # loiter index
        for i in range(4, NSeg-1): iLoiter.append(i)
        iClimb = [0, 2] # climb index

        constraints = []

        #----------------------------------------------------
        # Fuel weight model 

        MTOW = Variable('MTOW','lbf', 'max take off weight')
        W_end = VectorVariable(NSeg, 'W_{end}', 'lbf', 'segment-end weight')
        W_fuel = VectorVariable(NSeg, 'W_{fuel}', 'lbf', 'segment-fuel weight')
        W_zfw = Variable('W_{zfw}', 'lbf', 'Zero fuel weight')
        W_begin = W_end.left # define beginning of segment weight
        W_begin[0] = MTOW 

        # Payload model
        W_pay = Variable('W_{pay}', 10, 'lbf', 'Payload weight')
        Vol_pay = Variable('Vol_{pay}', 0.5, 'ft^3', 'Payload volume')

        # Avionics model
        W_avionics = Variable('W_{avionics}', 8, 'lbf', 'Avionics weight')
        Vol_avionics = Variable('Vol_{avionics}', 0.125, 'ft^3', 'Avionics volume')

        # end of first segment weight + first segment fuel weight must be greater 
        # than MTOW.  Each end of segment weight must be greater than the next end
        # of segment weight + the next segment fuel weight. The last end segment
        # weight must be greater than the zero fuel weight

        constraints.extend([MTOW >= W_end[0] + W_fuel[0], 
                            W_end[:-1] >= W_end[1:] + W_fuel[1:], 
                            W_end[-1] >= W_zfw])
        
        #----------------------------------------------------
        # Steady level flight model
        t = VectorVariable(NSeg, 't', 'days', 'time per flight segment')
        h = VectorVariable(NSeg, 'h', 'm', 'altitude')
        CD = VectorVariable(NSeg, 'C_D', '-', 'Drag coefficient')
    	CL = VectorVariable(NSeg, 'C_L', '-', 'Lift coefficient')
        V = VectorVariable(NSeg, 'V', 'm/s', 'cruise speed')
        rho = VectorVariable(NSeg, r'\rho', 'kg/m^3', 'air density')
        S = Variable('S', 'ft^2', 'wing area')
        eta_prop = VectorVariable(NSeg, r'\eta_{prop}', '-', 
                                  'propulsive efficiency')
        P_shaft = VectorVariable(NSeg, 'P_{shaft}', 'hp', 'Shaft power')
        T = VectorVariable(NSeg, 'T', 'lbf', 'Thrust')

        # Climb model
        h_dot = Variable('h_{dot}', 125, 'ft/min', 'Climb rate')
        
        constraints.extend([P_shaft == T*V/eta_prop, 
                            T >= 0.5*rho*V**2*CD*S, 
                            T[iClimb] >= 0.5*rho[iClimb]*V[iClimb]**2*CD[iClimb]*S + 
                                         W_begin[iClimb]*h_dot/V[iClimb], 
                            0.5*rho*CL*S*V**2 >= (W_end+W_begin)/2, 
                            eta_prop[iClimb] == 0.5, 
                            eta_prop[iCruise] == 0.6, 
                            eta_prop[iLoiter] == 0.7
                            ])
        # Propulsive efficiency variation with different flight segments, 
        # will change depending on propeller characteristics

        #----------------------------------------------------
        # altitude constraints
        h_station = Variable('h_{station}', 15000, 'ft', 'minimum altitude at station')
        h_min = Variable('h_{min}', 5000, 'ft', 'minimum cruise altitude')

        constraints.extend([h[iLoiter] == h_station, 
                            h[iCruise] == h_min, 
                            h[iClimb] == h_min, 
                            t[iClimb[0]]*h_dot >= h_min, 
                            # still need to determine min cruise altitude, 
                            #and make these variables independent of user-input numbers
                            t[iClimb[1]]*h_dot >= 10000*units('ft'), 
                            ])

        #----------------------------------------------------
        # Engine Model (DF35)

        W_engtot = Variable('W_{eng-tot}', 6, 'lbf', 'Installed engine weight')
                #conservative for 4.2 engine complete with prop, generator and structures
        BSFC_min = Variable('BSFC_{min}', 0.32, 'kg/kW/hr', 'Minimum BSFC')
        BSFC = VectorVariable(NSeg, 'BSFC', 'lb/hr/hp', 
                              'brake specific fuel consumption') 
        RPM_max = Variable('RPM_{max}', 9000, 'rpm', 'Maximum RPM')
        RPM = VectorVariable(NSeg, 'RPM', 'rpm', 'Engine operating RPM')
        P_shaftmax = VectorVariable(NSeg, 'P_{shaft-max}', 'hp', 
                                    'Max shaft power at altitude')
        P_shaftmaxMSL = Variable('P_{shaft-maxMSL}', 2.189, 'kW', 
                                 'Max shaft power at MSL')
        Lfactor = VectorVariable(NSeg, 'L_factor', '-', 'Max shaft power loss factor')
        V_max = VectorVariable(NSeg, 'V_{max}', 'm/s', 'maximum required speed')

        # Engine Weight Constraints
        constraints.extend([Lfactor >= 0.906**(1/0.15)*(h/h_station)**0.92, 
                            P_shaftmax/P_shaftmaxMSL + Lfactor <= 1, 
                            P_shaft <= P_shaftmax, 
                            (BSFC/BSFC_min)**0.129 >= 2*.486*(RPM/RPM_max)**-0.141 + \
                                                      0.0268*(RPM/RPM_max)**9.62, 
                            (P_shaft/P_shaftmax)**0.1 >= 0.999*(RPM/RPM_max)**0.292, 
                            RPM <= RPM_max, 
                            V_max[iLoiter] >= 38*units('m/s'),
                            P_shaftmax/P_shaft == (V_max/V)**(2), 
                            ])
        #rough maximum speed model, assuming constant propulsive efficiency and BSFC

        #----------------------------------------------------
        # Breguet Range
        z_bre = VectorVariable(NSeg, 'z_{bre}', '-', 'breguet coefficient')
        t_cruise = Variable('t_{cruise}', 1, 'days', 'time to station')
        t_station = Variable('t_{station}', 'days', 'time on station')
        R = Variable('R', 200, 'nautical_miles', 'range to station')
        g = Variable('g', 9.81, 'm/s^2', 'Gravitational acceleration')

        constraints.extend([z_bre >= V*t*BSFC*g*T/W_end/eta_prop, 
                            R <= V[iCruise]*t[iCruise], 
                            t[iLoiter] >= t_station/NLoiter, 
                            t[iCruise[0]] <= t_cruise, 
                            W_fuel/W_end >= te_exp_minus1(z_bre, 3)])

        #----------------------------------------------------
        # Aerodynamics model

        CLmax = Variable('C_{L-max}', 1.5, '-', 'Maximum lift coefficient')
        e = Variable('e', 0.9, '-', 'Spanwise efficiency')
        AR = Variable('AR', '-', 'Aspect ratio')
        b = Variable('b', 'ft', 'Span')
        mu = Variable(r'\mu', 1.5e-5, 'N*s/m^2', 'Dynamic viscosity')
        Re = VectorVariable(NSeg, 'Re', '-', 'Reynolds number')
        Cf = VectorVariable(NSeg, 'C_f', '-', 'wing skin friction coefficient')
        Kwing = Variable('K_{wing}', 1.3, '-', 'wing form factor')
        cl_16 = Variable('cl_{16}', 0.0001, '-', 'profile stall coefficient')

        # fuselage drag 
        Kfuse = Variable('K_{fuse}', 1.1, '-', 'Fuselage form factor')
        S_fuse = Variable('S_{fuse}', 'ft^2', 'Fuselage surface area')
        Cffuse = Variable('C_{f-fuse}', '-', 'Fuselage skin friction coefficient')
        CDfuse = Variable('C_{D-fuse}', '-', 'fueslage drag')
        l_fuse = Variable('l_{fuse}', 'ft', 'fuselage length')
        Refuse = Variable('Re_{fuse}', '-', 'fuselage Reynolds number')

        constraints.extend([CD >= CDfuse + 2*Cf*Kwing + CL**2/(pi*e*AR)
                                + cl_16*CL**16, 
                            b**2 == S*AR, 
                            CL <= CLmax, 
                            Re == rho*V/mu*(S/AR)**0.5, 
                            Cf >= 0.074/Re**0.2, 
                            CDfuse >= Kfuse*S_fuse*Cffuse/S, 
                            Refuse == rho*V/mu*l_fuse, 
                            Cffuse >= 0.074/Refuse**0.2, 
                            ])

        #----------------------------------------------------
        # landing gear
        #A_rearland = Variable('A_{rear-land}', 6, 'in^2',
        #                      'rear landing gear frontal area')
        #A_frontland = Variable('A_{front-land}', 6, 'in^2', 
        #                       'front landing gear frontal area')
        #CDland = Variable('C_{D-land}', 0.2, '-', 'drag coefficient landing gear')
        #CDAland = Variable('CDA_{land}', '-', 'normalized drag coefficient landing gear')

        #constraints.extend([CD >= CDfuse + 2*Cf*Kwing + CL**2/(pi*e*AR)
        #                        + cl_16*CL**16 + CDAland, 
        #                    CDAland >= (2*CDland*A_rearland + CDland*A_frontland)/S]) 

        #----------------------------------------------------
        # Atmosphere model
        gamma = Variable(r'\gamma', 1.4, '-', 'Heat capacity ratio of air')
        p_sl = Variable('p_{sl}', 101325, 'Pa', 'Pressure at sea level')
        T_sl = Variable('T_{sl}', 288.15, 'K', 'Temperature at sea level')
        L_atm = Variable('L_{atm}', 0.0065, 'K/m', 'Temperature lapse rate')
        T_atm = VectorVariable(NSeg, 'T_{atm}', 'K', 'Air temperature')
        a_atm = VectorVariable(NSeg, 'a_{atm}', 'm/s', 'Speed of sound at altitude')
        R_spec = Variable('R_{spec}', 287.058, 'J/kg/K', 'Specific gas constant of air')
        TH = (g/R_spec/L_atm).value.magnitude  # dimensionless
        rho_sl = Variable(r'\rho_{sl}', 1.225, 'kg/m^3', 'density of air at sea level')
        h_ref = Variable('h_{ref}', 5500, 'm', 'reference height for atm model')

        constraints.extend([#T_sl >= T_atm + L_atm*h,     # Temp decreases w/ altitude
                            #rho == p_sl*T_atm**(TH-1)/R_spec/(T_sl**TH)])
                            rho[iClimb[0]] == 1.055*units('kg/m^3'),
                            rho[iCruise] == 1.055*units('kg/m^3'),
                            rho[iClimb[1]] == 0.7377*units('kg/m^3'),
                            rho[iLoiter] == 0.7377*units('kg/m^3')])
                            #(rho/rho_sl) == 0.66*(h/h_ref)**-0.141])
            # http://en.wikipedia.org/wiki/Density_of_air#Altitude

        #----------------------------------------------------
        # Weight breakdown

        W_cent = Variable('W_{cent}', 'lbf', 'Center aircraft weight')
        W_fuse = Variable('W_{fuse}', 'lbf', 'fuselage weight') 
        W_wing = Variable('W_{wing}', 'lbf', 'Total wing structural weight')
        W_fueltot = Variable('W_{fuel-tot}', 'lbf', 'total fuel weight')
        m_fuse = Variable('m_{fuse}', 'kg', 'fuselage mass')
        m_cap = Variable('m_{cap}', 'kg', 'Cap mass')
        m_skin = Variable('m_{skin}', 'kg', 'Skin mass')
        m_tail = Variable('m_{tail}', 0.75, 'kg', 'tail mass')

        constraints.extend([W_wing >= m_skin*g + m_cap*g, 
                            W_fuse >= m_fuse*g, 
                            W_fueltot >= W_fuel.sum(),
                            W_cent >= W_fueltot + W_pay + W_engtot + W_fuse + W_avionics, 
                            W_zfw >= W_pay + W_engtot + W_fuse + W_wing + m_tail*g +
                                     W_avionics]) 

        #----------------------------------------------------
        # Structural model

        # Structural parameters
        rho_skin = Variable(r'\rho_{skin}', 0.1, 'g/cm^2', 'Wing Skin Density') 
        rho_cap = Variable(r'\rho_{cap}', 1.76, 'g/cm^3', 'Density of CF cap')
        E_cap = Variable('E_{cap}', 2e7, 'psi', 'Youngs modulus of CF cap')
        sigma_cap = Variable(r'\sigma_{cap}', 475e6, 'Pa', 'Cap stress') 
        
        # Structural lengths
        h_spar = Variable('h_{spar}', 'm', 'Spar height') 
        t_cap = Variable('t_{cap}', 0.028, 'in', 'Spar cap thickness') 
        #arbitrarily placed based on available cf
        w_cap = Variable('w_{cap}', 'in', 'Spar cap width')
        c = Variable('c', 'ft', 'Wing chord') #assumes straight, untapered wing

        # Structural ratios
        tau = Variable(r'\tau', 0.12, '-', 'Airfoil thickness ratio') #find better number
        LoverA = Variable('LoverA', 'lbf/ft^2', 'Wing loading')
        lambda_c = Variable(r'\lambda_c', '-', 'Taper ratio')

        # Structural areas
        A_capcent = Variable('A_{capcent}', 'm**2', 'Cap area at center')
        A_cap = Variable('A_{cap}', 'm**2', 'Cap area') #currently assumes constant area

        # Structural volumes
        Vol_cap = Variable('Vol_{cap}', 'm**3', 'Cap volume')

        # Structural evaluation parameters
        M_cent = Variable('M_cent', 'N*m', 'Center bending moment')
        F = Variable('F', 'N', 'Load on wings')
        SL = Variable('SL', 'Pa', 'Shear load') #need to add constraint
        N_Max = Variable('N_{Max}', 5, '-', 'Load factor') 
        #load rating for max number of g's
        P_cap = Variable('P_{cap}', 'N', 'Cap load')
        delta_tip = Variable(r'\delta_{tip}', 'ft', 'Tip deflection') 
        #need to add constraint

        constraints.extend([m_skin >= rho_skin*S*2, 
                            F >= W_cent*N_Max, 
                            c == S/b, 
                            M_cent >= b*F/8, 
                            P_cap >= M_cent/h_spar, 
                            A_capcent >= P_cap/sigma_cap, 
                            Vol_cap >= A_capcent*b/3, 
                            m_cap == rho_cap*Vol_cap, 
                            h_spar <= tau*c, 
                            w_cap == A_capcent/t_cap, 
                            LoverA == MTOW/S, 
                            delta_tip == b**2*sigma_cap/(4*E_cap*h_spar), 
                            delta_tip <= b/5]) 

        #----------------------------------------------------
        # Fuselage model

        # Constants
        rho_fuel = Variable(r'\rho_{fuel}', 6.01, 'lbf/gallon', 'density of 100LL')

        # Non-dimensional variables
        k1fuse = Variable('k_{1-fuse}', 2.5, '-', 'fuselage form factor 1')
        k2fuse = Variable('k-{2-fuse}', 20, '-', 'fuselage form factor 2')

        # Volumes
        Vol_fuel = Variable('Vol_{fuel}', 'm**3', 'Fuel Volume')
        Vol_fuse = Variable('Vol_{fuse}', 'm**3', 'fuselage volume')



        constraints.extend([m_fuse >= S_fuse*rho_skin, 
                            (l_fuse/k1fuse)**3 == Vol_fuse, 
                            (S_fuse/k2fuse)**3 == Vol_fuse**2, 
                            Vol_fuel >= W_fuel.sum()/rho_fuel, 
                            Vol_fuse >= Vol_fuel+Vol_avionics+Vol_pay])

        #----------------------------------------------------
        # wind speed model

        V_wind = Variable('V_{wind}', 25, 
                                'm/s', 'wind speed')

        constraints.extend([V[iLoiter] >= V_wind])

        objective = 1/t_station 
        return objective, constraints

if __name__ == '__main__':
    M = GasPoweredHALE()
    sol = M.solve('cvxopt')

    #----------------------------------------------
    # post processing
    
    #M.substitutions.update({'MTOW': ('sweep', np.linspace(70, 150, 15))})
    #sol = M.solve(solver='mosek', verbosity=0, skipsweepfailures=True)
    #
    #MTOW = sol('MTOW')
    #t_station = sol('t_{station}')

    #plt.close()
    #plt.plot(MTOW, t_station)
    #plt.xlabel('MTOW [lbf]')
    #plt.ylabel('t_station [days]')
    #plt.grid()
    #plt.savefig('tvsMTOW.png')

    #M.substitutions.update({'R':('sweep', np.linspace(100, 600, 15)), 'MTOW':85})
    #sol = M.solve(solver='mosek', verbosity=0, skipsweepfailures=True)

    #R = sol('R')
    #t_station = sol('t_{station}')

    #plt.close()
    #plt.plot(R, t_station)
    #plt.xlabel('R [nm]')
    #plt.grid()
    #plt.ylabel('t_station [days]')
    #plt.savefig('tvsR.png')

    #M.substitutions.update({'h_{min}':('sweep',np.linspace(1000,15000,15)),r'\rho'[1]:[1.19,1.16, 1.12, 1.09, 1.06, 1.03, 0.99, 0.96, 0.94, 0.91, 0.88, 0.85, 0.82, 0.80, 0.77],'R':85})
    #sol = M.solve(solver='mosek', verbosity=0, skipsweepfailures=True)

    #h_min = sol('h_{min}')
    #t_station = sol('t_{station}')

    #plt.close()
    #plt.plot(h_min, t_station)
    #plt.xlabel('h_min [ft]')
    #plt.grid()
    #plt.ylabel('t_station [days]')
    #plt.savefig('tvsh_min.png')

    #M.substitutions.update({'h_{station}':('sweep', np.linspace(15000,20000, 15)), r'\rho' 'h_{min}':5000})
    #sol = M.solve(solver='mosek', verbosity=0, skipsweepfailures=True)

    #h_station = sol('h_{station}')
    #t_station = sol('t_{station}')

    #plt.close()
    #plt.plot(h_station, t_station)
    #plt.xlabel('h_station [lbf]')
    #plt.grid()
    #plt.ylabel('t_station [days]')
    #plt.savefig('tvsh_station.png')

    #M.substitutions.update({'V_{wind}':('sweep', np.linspace(1, 40, 40)), 'h_{station}':15000, 'MTOW': 87})
    #sol = M.solve(solver='mosek', verbosity=0, skipsweepfailures=True)

    #V_wind87 = sol('V_{wind}')
    #t_station87 = sol('t_{station}')

    #plt.close()

    #M.substitutions.update({'V_{wind}':('sweep', np.linspace(1, 40, 40)), 'h_{station}':15000, 'MTOW': 96})
    #sol = M.solve(solver='mosek', verbosity=0, skipsweepfailures=True)

    #V_wind96 = sol('V_{wind}')
    #t_station96 = sol('t_{station}')

    #plt.plot(V_wind87, t_station87, V_wind96, t_station96)
    #plt.xlabel('V_wind [m/s]')
    #plt.ylabel('t_station [days]')
    #plt.grid()
    #plt.savefig('tvsV_wind96.png')