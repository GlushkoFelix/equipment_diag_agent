export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 64

export type PasswordChecks = {
  length: boolean
  letter: boolean
  digit: boolean
  valid: boolean
}

export function passwordChecks(value: string): PasswordChecks {
  const length = value.length >= PASSWORD_MIN_LENGTH && value.length <= PASSWORD_MAX_LENGTH
  const letter = /[A-Za-z]/.test(value)
  const digit = /\d/.test(value)
  return { length, letter, digit, valid: length && letter && digit }
}
