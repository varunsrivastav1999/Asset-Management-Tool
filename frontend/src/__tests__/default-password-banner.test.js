import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DefaultPasswordBanner from '@/components/DefaultPasswordBanner.vue'
import { useAuthStore } from '@/stores/auth'

const mountBanner = () => mount(DefaultPasswordBanner, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })

describe('DefaultPasswordBanner', () => {
  it('asks the first-run admin to change the default password', () => {
    setActivePinia(createPinia())
    useAuthStore().setUser({ id: 1, must_change_password: true })
    const w = mountBanner()
    expect(w.text()).toContain('default password')
    expect(w.find('a').attributes('href')).toBe('/profile#password')
  })

  it('stays hidden once the password has been changed', () => {
    setActivePinia(createPinia())
    useAuthStore().setUser({ id: 1, must_change_password: false })
    expect(mountBanner().find('[data-testid="default-password-banner"]').exists()).toBe(false)
  })
})
