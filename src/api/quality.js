import axios from 'axios'

// A generated read-only audit artifact, not a live backend business statistic.
export async function getPoiQualityAudit() {
  const response = await axios.get(`${import.meta.env.BASE_URL}data-quality/poi-audit.json`, {
    timeout: 10000,
    responseType: 'json',
  })
  if (!response.data || response.data.schemaVersion !== 1) throw new Error('离线核验记录格式不正确')
  return response.data
}
