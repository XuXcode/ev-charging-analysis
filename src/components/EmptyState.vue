<script setup>
import ViewState from './ViewState.vue'
defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '数据接入后将在这里展示' },
  kind: { type: String, default: 'empty' },
})
</script>
<template>
  <ViewState :kind="kind" :title="title" :description="description"><slot /></ViewState>
</template>
