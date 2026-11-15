<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import { remindersApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import { renderTemplate, SAMPLE } from '@/utils/templating'

const open = defineModel('open', { type: Boolean })
const props = defineProps({ template: Object })
const emit = defineEmits(['saved'])
const ui = useUiStore()
const form = reactive({ name: '', subject: '', body: '', sms_text: '' })
const errors = ref({})
const saving = ref(false)
const variables = ref([])
const focused = ref('body')
const fields = {}

onMounted(async () => (variables.value = (await remindersApi.variables().catch(() => ({ variables: [] }))).variables))
watch(open, (v) => {
  if (!v) return
  errors.value = {}
  Object.assign(form, { name: props.template?.name || '', subject: props.template?.subject || '', body: props.template?.body || '', sms_text: props.template?.sms_text || '' })
})

/** Insert {{variable}} at the caret of the last focused field. */
function insert(key) {
  const token = `{{${key}}}`
  const el = fields[focused.value]
  const value = form[focused.value] || ''
  const start = el?.selectionStart ?? value.length
  const end = el?.selectionEnd ?? value.length
  form[focused.value] = value.slice(0, start) + token + value.slice(end)
  requestAnimationFrame(() => {
    el?.focus()
    el?.setSelectionRange?.(start + token.length, start + token.length)
  })
}
function bind(name) {
  return {
    onFocus: (e) => {
      focused.value = name
      fields[name] = e.target
    },
  }
}

const preview = computed(() => ({
  subject: renderTemplate(form.subject, SAMPLE).replace(/\s+/g, ' ').trim(),
  body: renderTemplate(form.body, SAMPLE),
  sms: renderTemplate(form.sms_text || form.subject, SAMPLE),
}))
const smsLength = computed(() => form.sms_text.length)

async function save() {
  saving.value = true
  errors.value = {}
  try {
    props.template ? await remindersApi.updateTemplate(props.template.id, form) : await remindersApi.createTemplate(form)
    ui.success('Template saved')
    emit('saved')
    open.value = false
  } catch (e) {
    const { message, fields: f } = parseError(e)
    errors.value = f
    ui.error(message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal v-model:open="open" :title="template ? `Edit “${template.name}”` : 'New template'" size="xl">
    <div class="grid gap-5 lg:grid-cols-2">
      <form id="tpl-form" class="space-y-4" @submit.prevent="save">
        <AppInput v-model="form.name" label="Template name" required :error="errors.name" />
        <AppInput v-model="form.subject" label="Email subject" required :error="errors.subject" v-bind="bind('subject')" />
        <AppInput v-model="form.body" label="Email body" textarea :rows="8" required :error="errors.body" v-bind="bind('body')" />
        <div>
          <AppInput v-model="form.sms_text" label="SMS / in-app text" maxlength="160" :error="errors.sms_text" v-bind="bind('sms_text')" />
          <p class="mt-1 text-right text-xs" :class="smsLength > 140 ? 'text-warning' : 'text-muted'">{{ smsLength }}/160 · links are appended automatically</p>
        </div>
        <div>
          <p class="label">Insert a variable <span class="normal-case">(into {{ focused.replace('_', ' ') }})</span></p>
          <div class="flex flex-wrap gap-1.5">
            <button v-for="v in variables" :key="v.key" type="button" class="chip bg-primary-soft text-primary transition hover:brightness-110" :title="v.label" @mousedown.prevent @click="insert(v.key)">{{ v.key }}</button>
          </div>
        </div>
      </form>
      <aside class="space-y-3" aria-live="polite">
        <p class="label">Live preview (sample data)</p>
        <div class="rounded-2xl border border-line bg-white p-4 text-slate-900">
          <p class="text-xs text-slate-500">Subject</p>
          <p class="font-semibold">{{ preview.subject || '—' }}</p>
          <hr class="my-3 border-slate-200" />
          <p class="text-sm whitespace-pre-line">{{ preview.body || '—' }}</p>
        </div>
        <div class="ml-auto max-w-xs rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-sm text-primary-ink">
          {{ preview.sms || '—' }}
        </div>
      </aside>
    </div>
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
      <AppButton type="submit" form="tpl-form" :loading="saving">Save template</AppButton>
    </template>
  </AppModal>
</template>
