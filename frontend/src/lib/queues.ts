/** Riot queue ids the app knows by name. */
export const QUEUES: { id: number; label: string }[] = [
  { id: 400, label: 'Normal Draft' },
  { id: 420, label: 'Ranked Solo/Duo' },
  { id: 440, label: 'Ranked Flex' },
  { id: 490, label: 'Quickplay' },
  { id: 450, label: 'ARAM' },
]

export const queueName = (id: number) => QUEUES.find((q) => q.id === id)?.label ?? `Queue ${id}`

export const formatDuration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
