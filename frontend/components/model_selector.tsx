'use client';

import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

import { IconCheckCircleFill, IconChevronDown } from '@/components/ui/icons';
import type { Session } from '@/lib/types';

export function ModelSelector({
  session: _session,
  selectedModelId,
  onModelChange,
  className,
}: {
  session: Session;
  selectedModelId?: string;
  onModelChange?: (modelId: string) => void;
} & React.ComponentProps<typeof Button>) {
  const DEFAULT_MODEL_ID = 'claude-opus-4.8';

  const availableChatModels = useMemo(
    () => [
      {
        id: 'claude-opus-4.8',
        name: 'Claude Opus 4.8',
        description: 'Most capable model for complex agentic research',
      },
      {
        id: 'claude-4.6',
        name: 'Claude 4.6',
        description: 'Most advanced model with state-of-the-art capabilities',
      },
    ],
    [],
  );

  const availableModelIds = useMemo(
    () => availableChatModels.map((model) => model.id),
    [availableChatModels],
  );

  const [open, setOpen] = useState(false);
  const [currentModelId, setCurrentModelId] = useState(() => {
    const initialModelId = selectedModelId ?? DEFAULT_MODEL_ID;
    return availableModelIds.includes(initialModelId)
      ? initialModelId
      : DEFAULT_MODEL_ID;
  });

  const selectedChatModel = useMemo(
    () =>
      availableChatModels.find(
        (chatModel) => chatModel.id === currentModelId,
      ),
    [currentModelId, availableChatModels],
  );

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        asChild
        className={cn(
          'w-fit data-[state=open]:bg-accent data-[state=open]:text-accent-foreground',
          className,
        )}
      >
        <Button
          data-testid="model-selector"
          variant="outline"
          className="md:px-2 md:h-[34px]"
        >
          {selectedChatModel?.name}
          <IconChevronDown />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[300px]">
        {availableChatModels.map((chatModel) => {
          const { id } = chatModel;

          return (
            <DropdownMenuItem
              data-testid={`model-selector-item-${id}`}
              key={id}
              onSelect={() => {
                setOpen(false);
                setCurrentModelId(id);
                onModelChange?.(id);
                console.log('Selected model:', id);
              }}
              data-active={id === currentModelId}
              asChild
            >
              <button
                type="button"
                className="gap-4 group/item flex flex-row justify-between items-center w-full"
              >
                <div className="flex flex-col gap-1 items-start">
                  <div>{chatModel.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {chatModel.description}
                  </div>
                </div>

                <div className="text-foreground dark:text-foreground opacity-0 group-data-[active=true]/item:opacity-100">
                  <IconCheckCircleFill />
                </div>
              </button>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
