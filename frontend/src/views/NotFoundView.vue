<script setup>
import EmptyState from '@/components/EmptyState.vue'
</script>
<template>
  <EmptyState title="404 · 页面未找到" description="这个地址不在当前分析工作台中。"
    ><router-link to="/"><a-button type="primary">返回全省总览</a-button></router-link></EmptyState
  >
</template>
