<script setup>
defineProps({ title: String, description: String, compact: Boolean })
</script>
<template>
  <section class="panel analysis-slot" :class="{ compact }">
    <h2>{{ title }}</h2>
    <div class="analysis-slot-state">
      <span>待接入</span>
      <p>{{ description }}</p>
    </div>
    <slot />
  </section>
</template>
<style scoped>
.analysis-slot {
  padding: 22px;
  min-height: 180px;
  display: flex;
  flex-direction: column;
}
.analysis-slot h2 {
  margin: 0;
  font-size: 16px;
  color: #243b35;
  font-weight: 650;
}
.analysis-slot-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding-top: 20px;
}
.analysis-slot-state > span {
  align-self: flex-start;
  font-size: 12px;
  color: #52685c;
  border: 1px solid #d5e1d9;
  border-radius: 4px;
  padding: 3px 8px;
  background: #f4f8f5;
}
.analysis-slot-state p {
  font-size: 13px;
  line-height: 1.8;
  color: #52685c;
  margin: 12px 0 0;
}
.compact {
  min-height: 145px;
}
</style>
