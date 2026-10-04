/** Resolve only known counties: malformed or mismatched scope must not query province POIs. */
export function districtMapScope(districtCode, cityCode, catalog = []) {
  if (!districtCode || !cityCode) return null
  const district = catalog.find((row) => row.code === districtCode && row.cityCode === cityCode)
  return district ? { cityCode, districtCode, name: district.name } : null
}

export function searchLoadedStations(stations, text, limit = 8) {
  const query = text.trim().toLocaleLowerCase()
  if (!query) return { total: 0, items: [] }
  const matches = stations.filter((station) =>
    [station.name, station.address, station.poiId].some((value) =>
      String(value || '')
        .toLocaleLowerCase()
        .includes(query),
    ),
  )
  return { total: matches.length, items: matches.slice(0, limit) }
}
