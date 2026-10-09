import { createRouter, createWebHistory } from 'vue-router'
import { topics } from '@/config/topics'
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'overview',
      component: () => import('@/views/OverviewView.vue'),
      meta: { title: '全省总览' },
    },
    {
      path: '/city/:cityCode',
      name: 'city',
      component: () => import('@/views/CityView.vue'),
      meta: { title: '市州详情' },
    },
    {
      path: '/analysis/:topic',
      name: 'analysis',
      component: () => import('@/views/AnalysisView.vue'),
      beforeEnter: (to) =>
        topics.some((t) => t.slug === to.params.topic) ? true : { name: 'not-found' },
      meta: { title: '专题分析' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { title: '页面未找到' },
    },
  ],
  scrollBehavior: (to, from, saved) => saved || (to.path === from.path ? false : { top: 0 }),
})
router.beforeEach((to) => {
  if (to.name === 'analysis' && !topics.some((topic) => topic.slug === to.params.topic))
    return {
      name: 'not-found',
      params: { pathMatch: to.path.slice(1).split('/') },
      query: to.query,
    }
})
router.afterEach((to, from) => {
  const title =
    to.name === 'analysis' ? topics.find((t) => t.slug === to.params.topic)?.title : to.meta.title
  document.title = `${title || to.meta.title} · 湖南充电设施空间分布与可达性分析平台`
  if (to.path === from.path) return
  requestAnimationFrame(() =>
    document.querySelector('#main-content')?.focus({ preventScroll: true }),
  )
})
export default router
