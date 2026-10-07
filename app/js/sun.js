// Sun times computed on the phone (NOAA solar position equations, after Meeus).
// The pipeline ships sunrise/sunset from Open-Meteo; first and last light
// (civil twilight, sun 6 degrees below the horizon) are computed here.
// Accuracy is about a minute for California latitudes.

const RAD = Math.PI / 180;
const DAY = 86400;

// Sun altitude (degrees) that defines each event.
export const ALTITUDE = {
  sunrise: -0.833, // upper limb on the horizon, with refraction
  civil: -6,       // first / last light
};

function solar(unix) {
  const jd = unix / DAY + 2440587.5;
  const T = (jd - 2451545) / 36525;
  const L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360;
  const M = 357.52911 + T * (35999.05029 - 0.0001537 * T);
  const e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T);
  const Mr = M * RAD;
  const C = Math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T))
    + Math.sin(2 * Mr) * (0.019993 - 0.000101 * T)
    + Math.sin(3 * Mr) * 0.000289;
  const omega = (125.04 - 1934.136 * T) * RAD;
  const lambda = (L0 + C - 0.00569 - 0.00478 * Math.sin(omega)) * RAD;
  const eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60;
  const eps = (eps0 + 0.00256 * Math.cos(omega)) * RAD;
  const decl = Math.asin(Math.sin(eps) * Math.sin(lambda));
  const y = Math.tan(eps / 2) ** 2;
  const L0r = L0 * RAD;
  // Equation of time, minutes.
  const eqTime = 4 / RAD * (y * Math.sin(2 * L0r) - 2 * e * Math.sin(Mr)
    + 4 * e * y * Math.sin(Mr) * Math.cos(2 * L0r)
    - 0.5 * y * y * Math.sin(4 * L0r) - 1.25 * e * e * Math.sin(2 * Mr));
  return { decl, eqTime };
}

// Unix time of a sun event on the day containing `localNoon` (unix seconds,
// roughly local solar noon). rising=true for morning events. Returns null in
// polar day/night (never happens in California, but don't return garbage).
export function sunEvent(localNoon, lat, lon, altitude, rising) {
  const utcDay = Math.floor(localNoon / DAY) * DAY;
  let t = localNoon;
  for (let i = 0; i < 3; i++) {
    const { decl, eqTime } = solar(t);
    const cosH = (Math.sin(altitude * RAD) - Math.sin(lat * RAD) * Math.sin(decl))
      / (Math.cos(lat * RAD) * Math.cos(decl));
    if (cosH < -1 || cosH > 1) return null;
    const H = Math.acos(cosH) / RAD;
    const minutes = 720 - 4 * (lon + (rising ? H : -H)) - eqTime;
    t = utcDay + minutes * 60;
  }
  return Math.round(t);
}

// All four times for the local day starting at `localMidnight` (unix seconds).
export function sunTimes(localMidnight, lat, lon) {
  const noon = localMidnight + 12 * 3600;
  return {
    firstLight: sunEvent(noon, lat, lon, ALTITUDE.civil, true),
    sunrise: sunEvent(noon, lat, lon, ALTITUDE.sunrise, true),
    sunset: sunEvent(noon, lat, lon, ALTITUDE.sunrise, false),
    lastLight: sunEvent(noon, lat, lon, ALTITUDE.civil, false),
  };
}
