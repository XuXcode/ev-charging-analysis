import AMapLoader from '@amap/amap-jsapi-loader'
let loader
export function loadAMap() {
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) return Promise.reject(new Error('未配置高德 Key，使用本地边界地图'))
  if (!loader) {
    const serviceHost = import.meta.env.VITE_AMAP_SECURITY_SERVICE_HOST
    window._AMapSecurityConfig = serviceHost
      ? { serviceHost }
      : {
          securityJsCode:
            import.meta.env.VITE_AMAP_SECURITY_JS_CODE ||
            import.meta.env.VITE_AMAP_SECURITY_CODE ||
            '',
        }
    loader = AMapLoader.load({
      key,
      version: '2.0',
      plugins: [
        'AMap.Scale',
        'AMap.ToolBar',
        'AMap.HeatMap',
        'AMap.MarkerCluster',
        'AMap.DistrictSearch',
      ],
    }).catch((error) => {
      loader = null
      throw error
    })
  }
  return loader
}
