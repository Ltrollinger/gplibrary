import pandas as pd

def get_windspeed(latitude, perc, altitude):
    h = altitude*0.3048
    p = 101325/100*(1 - 2.25577e-5*h)**5.25588
    pressures = [550, 650]
    for mb in pressures:
        if abs(mb-p) < 15:
            filename = "wind%d.csv" % mb
    if not filename:
        print "Altitude not close enough to known values"
    df = pd.read_csv(filename)
    wind = df[df["Latitude"] == latitude]["perc%d" % perc].item()
    return wind
