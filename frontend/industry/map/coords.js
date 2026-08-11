/** 坐标与轻微抖动（避免同址 Marker 完全重叠）。 */

export function jitter(seed) {
  const n = Number(String(seed).replace(/\D/g, "").slice(-4) || "0");
  const a = ((n % 17) - 8) * 0.00025;
  const b = ((Math.floor(n / 17) % 17) - 8) * 0.00025;
  return [a, b];
}

/** 静态省中心点（WGS-84 近似）→ GCJ-02。 */
export function wgs84ToGcj02(lng, lat) {
  const PI = Math.PI;
  const A = 6378245.0;
  const EE = 0.00669342162296594323;
  const outOfChina =
    lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271;
  if (outOfChina) return [lng, lat];

  function transformLat(x, y) {
    let ret =
      -100.0 +
      2.0 * x +
      3.0 * y +
      0.2 * y * y +
      0.1 * x * y +
      0.2 * Math.sqrt(Math.abs(x));
    ret +=
      ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) /
      3.0;
    ret +=
      ((20.0 * Math.sin(y * PI) + 40.0 * Math.sin((y / 3.0) * PI)) * 2.0) / 3.0;
    ret +=
      ((160.0 * Math.sin((y / 12.0) * PI) + 320 * Math.sin((y * PI) / 30.0)) *
        2.0) /
      3.0;
    return ret;
  }
  function transformLng(x, y) {
    let ret =
      300.0 +
      x +
      2.0 * y +
      0.1 * x * x +
      0.1 * x * y +
      0.1 * Math.sqrt(Math.abs(x));
    ret +=
      ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) /
      3.0;
    ret +=
      ((20.0 * Math.sin(x * PI) + 40.0 * Math.sin((x / 3.0) * PI)) * 2.0) / 3.0;
    ret +=
      ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x / 30.0) * PI)) *
        2.0) /
      3.0;
    return ret;
  }

  let dLat = transformLat(lng - 105.0, lat - 35.0);
  let dLng = transformLng(lng - 105.0, lat - 35.0);
  const radLat = (lat / 180.0) * PI;
  let magic = Math.sin(radLat);
  magic = 1 - EE * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * PI);
  dLng = (dLng * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * PI);
  return [lng + dLng, lat + dLat];
}

/** @returns {[lng, lat]|null} */
export function toAmapLngLat(lat, lng, coordSystem) {
  const la = Number(lat);
  const ln = Number(lng);
  if (!Number.isFinite(la) || !Number.isFinite(ln)) return null;
  if (String(coordSystem || "").toLowerCase() === "gcj02") {
    return [ln, la];
  }
  return wgs84ToGcj02(ln, la);
}
