import { describe, expect, it } from 'vitest'
import { parseError } from '@/api/http'

const err = (status, data) => ({ response: { status, data } })

describe('parseError', () => {
  it('handles network failures and timeouts', () => {
    expect(parseError({}).message).toMatch(/Network error/)
    expect(parseError({ code: 'ECONNABORTED' }).message).toMatch(/timed out/)
  })

  it('uses detail when present', () => {
    expect(parseError(err(400, { detail: 'Nope', code: 'invalid' })).message).toBe('Nope')
  })

  it('flattens field errors and builds a message from the first one', () => {
    const { message, fields } = parseError(err(400, { serial_number: ['Already exists.'], name: ['Required.'] }))
    expect(fields).toEqual({ serial_number: 'Already exists.', name: 'Required.' })
    expect(message).toBe('serial number: Already exists.')
  })

  it('keeps nested objects (custom field errors) intact', () => {
    const { fields, message } = parseError(err(400, { custom_data: { ram_gb: 'RAM is required.' } }))
    expect(fields.custom_data).toEqual({ ram_gb: 'RAM is required.' })
    expect(message).toMatch(/highlighted/)
  })

  it('hides raw HTML server errors', () => {
    expect(parseError(err(500, '<html>boom</html>')).message).toMatch(/Something went wrong/)
  })
})
