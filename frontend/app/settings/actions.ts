'use server'

import { auth } from '@/auth'
import { getUser } from '@/app/login/actions'
import { AccessInfo, SettingsSnapshot, User } from '@/lib/types'
import { getStringFromBuffer } from '@/lib/utils'
import { kv } from '@vercel/kv'

type LimitPeriod = 'day' | 'week' | 'month'

const FREE_QUESTION_LIMIT_ENABLED = getFreeQuestionLimitEnabled()
const FREE_QUESTION_LIMIT_PERIOD = getFreeQuestionLimitPeriod()
const FREE_QUESTION_LIMIT = FREE_QUESTION_LIMIT_ENABLED ? getFreeQuestionLimit() : 0

type UserSettingsRecord = {
  anthropicApiKey?: string
  anthropicKeySetAt?: number
}

const getSettingsKey = (userId: string) => `user:settings:${userId}`
const getUsageKey = (userId: string) => `usage:${userId}`

function parseBoolean(value: any) {
  return value === true || value === 'true'
}

function getFreeQuestionLimitEnabled() {
  const rawValue =
    process.env.FREE_QUESTION_LIMIT_ENABLED ?? process.env.DAILY_FREE_QUESTION_LIMIT_ENABLED
  if (typeof rawValue === 'undefined') {
    return true
  }

  return rawValue === 'true' || rawValue === '1'
}

function getFreeQuestionLimit() {
  const rawValue = process.env.FREE_QUESTION_LIMIT ?? process.env.DAILY_FREE_QUESTION_LIMIT
  const parsedValue = rawValue ? parseInt(rawValue, 10) : NaN

  if (!rawValue) {
    throw new Error('FREE_QUESTION_LIMIT env var is required')
  }

  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    throw new Error('FREE_QUESTION_LIMIT must be a positive integer')
  }

  return parsedValue
}

function normalizeLimitPeriod(value: string | undefined): LimitPeriod {
  if (!value) return 'day'

  const normalized = value.trim().toLowerCase()
  if (['day', 'daily', 'd'].includes(normalized)) return 'day'
  if (['week', 'weekly', 'w'].includes(normalized)) return 'week'
  if (['month', 'monthly', 'm'].includes(normalized)) return 'month'

  throw new Error('FREE_QUESTION_LIMIT_PERIOD must be one of: day, week, month')
}

function getFreeQuestionLimitPeriod(): LimitPeriod {
  const rawValue =
    process.env.FREE_QUESTION_LIMIT_PERIOD ?? process.env.DAILY_FREE_QUESTION_LIMIT_PERIOD
  return normalizeLimitPeriod(rawValue)
}

function getPeriodBounds(period: LimitPeriod) {
  const start = new Date()
  start.setHours(0, 0, 0, 0)

  switch (period) {
    case 'day': {
      break
    }
    case 'week': {
      const day = start.getDay()
      const diffFromMonday = (day + 6) % 7 // convert Sunday=0 to Monday=0
      start.setDate(start.getDate() - diffFromMonday)
      break
    }
    case 'month': {
      start.setDate(1)
      break
    }
  }

  const end = new Date(start)
  if (period === 'day') {
    end.setHours(23, 59, 59, 999)
  } else if (period === 'week') {
    end.setDate(end.getDate() + 7)
    end.setMilliseconds(end.getMilliseconds() - 1)
  } else if (period === 'month') {
    end.setMonth(end.getMonth() + 1)
    end.setMilliseconds(end.getMilliseconds() - 1)
  }

  return { start, end }
}

function formatMaskedAnthropicKey(key: string) {
  const prefix = key.slice(0, 16)
  const suffix = key.slice(-4)
  return `${prefix}...${suffix}`
}

async function getUserByEmail(email: string) {
  const user = await getUser(email)
  return user as User | null
}

async function getSettingsForUser(userId: string) {
  const settings = await kv.hgetall<UserSettingsRecord>(getSettingsKey(userId))
  return settings || {}
}

export async function getAnthropicApiKeyForUser(userId: string) {
  const settings = await getSettingsForUser(userId)
  return settings?.anthropicApiKey ?? null
}

export async function getQuestionCountForPeriod(userId: string) {
  const usageKey = getUsageKey(userId)
  const { start, end } = getPeriodBounds(FREE_QUESTION_LIMIT_PERIOD)

  const count = await kv.zcount(usageKey, start.getTime(), end.getTime())
  return typeof count === 'number' ? count : 0
}

export async function claimQuestionSlot(userId: string, chatId?: string) {
  const settings = await getSettingsForUser(userId)
  const hasAnthropicKey = !!settings?.anthropicApiKey

  if (!FREE_QUESTION_LIMIT_ENABLED) {
    return {
      allowed: true,
      hasAnthropicKey,
      count: 0,
      limit: 0,
      limitPeriod: FREE_QUESTION_LIMIT_PERIOD
    }
  }

  const usageKey = getUsageKey(userId)
  const now = Date.now()
  const { start } = getPeriodBounds(FREE_QUESTION_LIMIT_PERIOD)

  if (hasAnthropicKey) {
    await kv.zadd(usageKey, {
      score: now,
      member: `${chatId ?? 'unknown'}:${now}`
    })

    return {
      allowed: true,
      hasAnthropicKey: true,
      count: 0,
      limit: FREE_QUESTION_LIMIT,
      limitPeriod: FREE_QUESTION_LIMIT_PERIOD
    }
  }

  await kv.zremrangebyscore(usageKey, 0, start.getTime() - 1)

  const currentCount = await getQuestionCountForPeriod(userId)
  if (currentCount >= FREE_QUESTION_LIMIT) {
    return {
      allowed: false,
      hasAnthropicKey: false,
      count: currentCount,
      limit: FREE_QUESTION_LIMIT,
      limitPeriod: FREE_QUESTION_LIMIT_PERIOD
    }
  }

  await kv.zadd(usageKey, {
    score: now,
    member: `${chatId ?? 'unknown'}:${now}`
  })

  return {
    allowed: true,
    hasAnthropicKey: false,
    count: currentCount + 1,
    limit: FREE_QUESTION_LIMIT,
    limitPeriod: FREE_QUESTION_LIMIT_PERIOD
  }
}

export async function getSettingsSnapshot(): Promise<SettingsSnapshot | null> {
  const session = await auth()

  if (!session?.user?.id || !session.user.email) {
    return null
  }

  return getSettingsSnapshotForUser(session.user.id, session.user.email)
}

export async function getSettingsSnapshotForUser(
  userId: string,
  email: string
): Promise<SettingsSnapshot> {
  const settings = await getSettingsForUser(userId)
  const usageCount = FREE_QUESTION_LIMIT_ENABLED
    ? await getQuestionCountForPeriod(userId)
    : 0
  const user = await getUserByEmail(email)

  const hasAnthropicKey = !!settings?.anthropicApiKey
  const emailVerified = parseBoolean(user?.emailVerified)
  const anthropicKeyMasked = settings?.anthropicApiKey
    ? formatMaskedAnthropicKey(settings.anthropicApiKey)
    : undefined

  const snapshot: SettingsSnapshot = {
    email,
    hasAnthropicKey,
    anthropicKeyLast4: settings?.anthropicApiKey
      ? settings.anthropicApiKey.slice(-6)
      : undefined,
    anthropicKeyMasked,
    limitsEnabled: FREE_QUESTION_LIMIT_ENABLED,
    limit: FREE_QUESTION_LIMIT,
    limitPeriod: FREE_QUESTION_LIMIT_PERIOD,
    usageCount: hasAnthropicKey || !FREE_QUESTION_LIMIT_ENABLED ? 0 : usageCount,
    emailVerified
  }

  return snapshot
}

export async function saveAnthropicApiKey(apiKey: string) {
  const session = await auth()

  if (!session?.user?.id) {
    return { type: 'error', message: 'You must be signed in.' }
  }

  const trimmedKey = apiKey.trim()

  if (!trimmedKey) {
    return { type: 'error', message: 'Please provide a valid Anthropic API key.' }
  }

  await kv.hset(getSettingsKey(session.user.id), {
    anthropicApiKey: trimmedKey,
    anthropicKeySetAt: Date.now()
  })

  return {
    type: 'success',
    message: 'Anthropic API key saved.',
    last4: trimmedKey.slice(-6),
    maskedKey: formatMaskedAnthropicKey(trimmedKey)
  }
}

export async function removeAnthropicApiKey() {
  const session = await auth()

  if (!session?.user?.id) {
    return { type: 'error', message: 'You must be signed in.' }
  }

  await kv.hdel(getSettingsKey(session.user.id), 'anthropicApiKey', 'anthropicKeySetAt')

  return {
    type: 'success',
    message: 'Anthropic API key removed.'
  }
}

export async function requestEmailVerification() {
  const session = await auth()

  if (!session?.user?.email) {
    return { type: 'error', message: 'You must be signed in.' }
  }

  const user = await getUserByEmail(session.user.email)
  if (!user) {
    return { type: 'error', message: 'User not found.' }
  }

  if (parseBoolean(user.emailVerified)) {
    return { type: 'success', message: 'Email already verified.' }
  }

  const code = Math.floor(100000 + Math.random() * 900000).toString()
  const expiresAt = Date.now() + 15 * 60 * 1000

  await kv.hset(`user:${session.user.email}`, {
    verificationCode: code,
    verificationExpiresAt: expiresAt
  })

  return {
    type: 'success',
    message: 'Verification code generated. Please check your email.',
    code
  }
}

export async function verifyEmailCode(code: string) {
  const session = await auth()

  if (!session?.user?.email) {
    return { type: 'error', message: 'You must be signed in.' }
  }

  const trimmedCode = code.trim()
  if (!trimmedCode) {
    return { type: 'error', message: 'Please enter the verification code.' }
  }

  const user = await getUserByEmail(session.user.email)
  if (!user?.verificationCode) {
    return { type: 'error', message: 'Request a verification code first.' }
  }

  const expiresAt = Number(user.verificationExpiresAt ?? 0)
  if (expiresAt && Date.now() > expiresAt) {
    return { type: 'error', message: 'Verification code has expired.' }
  }

  if (String(user.verificationCode) !== trimmedCode) {
    return { type: 'error', message: 'Verification code is incorrect.' }
  }

  await kv.hset(`user:${session.user.email}`, {
    emailVerified: true
  })
  await kv.hdel(
    `user:${session.user.email}`,
    'verificationCode',
    'verificationExpiresAt'
  )

  return { type: 'success', message: 'Email verified successfully.' }
}

export async function requestPasswordReset(email: string) {
  const trimmedEmail = email.trim()

  if (!trimmedEmail) {
    return { type: 'error', message: 'Email is required.' }
  }

  const user = await getUserByEmail(trimmedEmail)
  if (!user) {
    return { type: 'error', message: 'No account found for that email.' }
  }

  const code = Math.floor(100000 + Math.random() * 900000).toString()
  const expiresAt = Date.now() + 15 * 60 * 1000

  await kv.hset(`user:${trimmedEmail}`, {
    resetCode: code,
    resetCodeExpiresAt: expiresAt
  })

  return {
    type: 'success',
    message: 'Password reset code generated. Please check your email.',
    code
  }
}

export async function resetPasswordWithCode(
  email: string,
  code: string,
  newPassword: string
) {
  const trimmedEmail = email.trim()
  const trimmedCode = code.trim()
  const trimmedPassword = newPassword.trim()

  if (!trimmedEmail || !trimmedCode || !trimmedPassword) {
    return { type: 'error', message: 'All fields are required.' }
  }

  if (trimmedPassword.length < 6) {
    return {
      type: 'error',
      message: 'Password must be at least 6 characters long.'
    }
  }

  const user = await getUserByEmail(trimmedEmail)
  if (!user?.resetCode) {
    return { type: 'error', message: 'Request a reset code first.' }
  }

  const expiresAt = Number(user.resetCodeExpiresAt ?? 0)
  if (expiresAt && Date.now() > expiresAt) {
    return { type: 'error', message: 'Reset code has expired.' }
  }

  if (String(user.resetCode) !== trimmedCode) {
    return { type: 'error', message: 'Reset code is incorrect.' }
  }

  const salt = crypto.randomUUID()
  const encoder = new TextEncoder()
  const saltedPassword = encoder.encode(trimmedPassword + salt)
  const hashedPasswordBuffer = await crypto.subtle.digest('SHA-256', saltedPassword)
  const hashedPassword = getStringFromBuffer(hashedPasswordBuffer)

  await kv.hset(`user:${trimmedEmail}`, {
    password: hashedPassword,
    salt,
    resetCode: '',
    resetCodeExpiresAt: 0
  })

  return { type: 'success', message: 'Password updated successfully.' }
}
