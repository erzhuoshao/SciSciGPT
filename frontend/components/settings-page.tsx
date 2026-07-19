'use client'

import { useMemo, useState, useTransition } from 'react'
import Link from 'next/link'
import { saveAnthropicApiKey, removeAnthropicApiKey } from '@/app/settings/actions'
import { SettingsSnapshot } from '@/lib/types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

export function SettingsPage({ initialSettings }: { initialSettings: SettingsSnapshot }) {
  const [settings, setSettings] = useState(initialSettings)
  const [apiKey, setApiKey] = useState(initialSettings.anthropicKeyMasked ?? '')
  const [isPending, startTransition] = useTransition()

  const limitPeriodLabel = useMemo(() => {
    switch (settings.limitPeriod) {
      case 'week':
        return 'per week'
      case 'month':
        return 'per month'
      default:
        return 'per day'
    }
  }, [settings.limitPeriod])

  const remainingWindowLabel = useMemo(() => {
    switch (settings.limitPeriod) {
      case 'week':
        return 'this week'
      case 'month':
        return 'this month'
      default:
        return 'today'
    }
  }, [settings.limitPeriod])

  const remainingFreeQuestions = useMemo(() => {
    if (!settings.limitsEnabled) return 0
    return Math.max(0, settings.limit - settings.usageCount)
  }, [settings.limit, settings.usageCount, settings.limitsEnabled])

  const handleSaveApiKey = () => {
    startTransition(async () => {
      const response = await saveAnthropicApiKey(apiKey)
      if (response?.type === 'success') {
        toast.success(response.message)
        setSettings(prev => ({
          ...prev,
          hasAnthropicKey: true,
          anthropicKeyLast4: response.last4,
          anthropicKeyMasked: response.maskedKey,
          usageCount: 0
        }))
        setApiKey(response.maskedKey ?? '')
      } else if (response?.message) {
        toast.error(response.message)
      }
    })
  }

  const handleRemoveApiKey = () => {
    startTransition(async () => {
      const response = await removeAnthropicApiKey()
      if (response?.type === 'success') {
        toast.success(response.message)
        setSettings(prev => ({
          ...prev,
          hasAnthropicKey: false,
          anthropicKeyLast4: undefined,
          anthropicKeyMasked: undefined
        }))
        setApiKey('')
      } else if (response?.message) {
        toast.error(response.message)
      }
    })
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-6 shadow-sm dark:bg-zinc-950">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-xl font-semibold">Anthropic API key</h2>
            <p className="text-sm text-muted-foreground">
              Add your own Anthropic API key to unlock unlimited questions.
            </p>
          </div>
        </div>
        <div className="mt-4 space-y-3">
          <Label htmlFor="apiKey">Anthropic API key</Label>
          <Input
            id="apiKey"
            type="text"
            value={apiKey}
            onChange={event => setApiKey(event.target.value)}
            placeholder="sk-ant-..."
            readOnly={settings.hasAnthropicKey}
            disabled={isPending || settings.hasAnthropicKey}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={isPending || settings.hasAnthropicKey || !apiKey.trim()}
              onClick={handleSaveApiKey}
            >
              Save key
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={isPending || !settings.hasAnthropicKey}
              onClick={handleRemoveApiKey}
            >
              Remove key
            </Button>
            <Button
              asChild
              type="button"
              variant="secondary"
              className="bg-[#d4a37f] text-white hover:bg-[#c48f69] border-0"
            >
              <Link href="https://console.anthropic.com/settings/keys" target="_blank">
                Get a key from Anthropic
              </Link>
            </Button>
          </div>
          {!settings.hasAnthropicKey && settings.limitsEnabled && (
            <p className="text-xs text-muted-foreground">
              Free tier: {settings.limit} questions {limitPeriodLabel}. Remaining {remainingWindowLabel}:{' '}
              {remainingFreeQuestions}
            </p>
          )}
        </div>
      </section>

      {/* Email verification removed per request */}
    </div>
  )
}
