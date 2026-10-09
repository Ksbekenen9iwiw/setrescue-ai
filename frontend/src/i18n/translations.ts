export type Language = 'en' | 'id'

const translations = {
  en: {
    projects: 'Projects', dashboard: 'Dashboard', documents: 'Documents', prevent: 'PREVENT', schedule: 'Schedule',
    live: 'Live Production', incidents: 'Incidents', recovery: 'Recovery', crew: 'Crew Updates', reports: 'Reports', settings: 'Settings',
    readiness: 'Production readiness', runPrevent: 'Run PREVENT', generateSchedule: 'Generate schedule', reportIncident: 'Report incident',
    loading: 'Loading…', noData: 'Nothing here yet.', retry: 'Try again', verified: 'Verified fact', aiSuggested: 'AI suggestion',
    active: 'Active', blocked: 'Blocked', ready: 'Ready', review: 'Needs review', notReady: 'Not ready',
    loadDemo: 'Load realistic demo', newProject: 'New project', save: 'Save', cancel: 'Cancel', approve: 'Approve & apply',
    projectControl: 'Production control', stateVersion: 'State version', allClear: 'All systems connected',
    productionData: 'Production Data', allProjects: 'All projects', overview: 'Overview',
    scheduleLive: 'Schedule & Live', recover: 'Recovery & approval', aiSettings: 'AI settings',
  },
  id: {
    projects: 'Proyek', dashboard: 'Dasbor', documents: 'Dokumen', prevent: 'PREVENT', schedule: 'Jadwal',
    live: 'Produksi Langsung', incidents: 'Insiden', recovery: 'Pemulihan', crew: 'Pembaruan Kru', reports: 'Laporan', settings: 'Pengaturan',
    readiness: 'Kesiapan produksi', runPrevent: 'Jalankan PREVENT', generateSchedule: 'Buat jadwal', reportIncident: 'Laporkan insiden',
    loading: 'Memuat…', noData: 'Belum ada data.', retry: 'Coba lagi', verified: 'Fakta terverifikasi', aiSuggested: 'Saran AI',
    active: 'Aktif', blocked: 'Terhambat', ready: 'Siap', review: 'Perlu ditinjau', notReady: 'Belum siap',
    loadDemo: 'Muat demo realistis', newProject: 'Proyek baru', save: 'Simpan', cancel: 'Batal', approve: 'Setujui & terapkan',
    projectControl: 'Kendali produksi', stateVersion: 'Versi keadaan', allClear: 'Semua sistem terhubung',
    productionData: 'Data Produksi', allProjects: 'Semua proyek', overview: 'Ringkasan',
    scheduleLive: 'Jadwal & Langsung', recover: 'Pemulihan & persetujuan', aiSettings: 'Pengaturan AI',
  },
} as const

export type TranslationKey = keyof typeof translations.en

export function translate(language: Language, key: TranslationKey): string {
  return translations[language][key]
}
