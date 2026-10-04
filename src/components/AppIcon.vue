<script setup>
defineProps({ name: { type: String, default: 'map' }, size: { type: Number, default: 20 } })
const paths = {
  map: 'M3 5l6-2 6 2 6-2v16l-6 2-6-2-6 2V5m6-2v16m6-14v16',
  bolt: 'M13 2 4 14h7l-1 8 10-13h-7l0-7',
  station:
    'M5 21V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v16M3 21h15M8 7h5v5H8zM16 10h2l2 3v5a1 1 0 0 0 2 0v-8l-3-3',
  city: 'M3 21V8h7v13m0 0V3h8v18m0-10h3v10M1 21h22M6 11v1m0 3v1m8-9v1m0 3v1m0 3v1',
  speed: 'M3 18a10 10 0 1 1 18 0M12 13l5-5M5 14h2m10 0h2M12 3v3',
  bars: 'M4 20V12h4v8m4 0V4h4v16m4 0V8h2v12M2 20h22',
  chart: 'M3 3v18h18M6 16l4-6 5 3 6-8',
  time: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18m0 4v5l4 2',
  target:
    'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18m0 5a4 4 0 1 1 0 8 4 4 0 0 1 0-8M12 1v4m0 14v4M1 12h4m14 0h4',
  layers: 'M12 3 2 8l10 5 10-5-10-5M2 12l10 5 10-5M2 16l10 5 10-5',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  back: 'M20 12H4m6-6-6 6 6 6',
  info: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18m0 7v6m0-9v1',
  pin: 'M12 22s8-8 8-13a8 8 0 1 0-16 0c0 5 8 13 8 13m0-16a3 3 0 1 1 0 6 3 3 0 0 1 0-6',
  expand: 'M3 9V3h6m6 0h6v6m0 6v6h-6m-6 0H3v-6',
}
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.map" />
  </svg>
</template>
