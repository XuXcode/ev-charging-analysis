import axios from 'axios'
export const http = axios.create({
  baseURL: import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 15000,
})
http.interceptors.response.use(
  (response) => {
    const body = response.data
    return body && typeof body === 'object' && 'code' in body && 'data' in body ? body.data : body
  },
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    const message =
        error.response?.data?.message ||
        (typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '') ||
        (error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '数据请求失败，请检查接口连接'),
      failure = new Error(message)
    failure.status = error.response?.status
    failure.requestId = error.response?.headers?.['x-request-id']
    return Promise.reject(failure)
  },
)
