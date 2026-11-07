import { useState } from "react";
import { useListPersonas } from "@/api/generated/client";
import type { PersonaRole } from "@/api/generated/model";
import { setPersona, useAskingForName, usePersona } from "@/api/persona";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { roleLabel } from "@/lib/labels";

function NameForm({ initial, onDone }: { initial: string; onDone: (name: string) => void }) {
  const [name, setName] = useState(initial);
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) onDone(name.trim());
      }}
    >
      <Input
        autoFocus
        aria-label="Your name"
        placeholder="Your name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        className="w-44"
      />
      <Button type="submit" variant="primary" size="sm">
        Save name
      </Button>
    </form>
  );
}

/** The role picker and the name recorded on decisions. The name is asked for once. */
export function PersonaSwitcher() {
  const persona = usePersona();
  const asking = useAskingForName();
  const personas = useListPersonas();
  const [editing, setEditing] = useState(false);
  const options: { role: PersonaRole; label: string }[] = personas.data ?? [
    { role: persona.role, label: roleLabel(persona.role) },
  ];

  return (
    <div className="flex items-center gap-3">
      <Select
        aria-label="Role"
        value={persona.role}
        onChange={(event) => {
          const chosen = options.find((item) => item.role === event.target.value);
          if (chosen) setPersona({ ...persona, role: chosen.role });
        }}
      >
        {options.map((item) => (
          <option key={item.role} value={item.role}>
            {item.label}
          </option>
        ))}
      </Select>
      {persona.name && !editing && !asking ? (
        <button
          type="button"
          className="underline"
          onClick={() => setEditing(true)}
          title="Change name"
        >
          {persona.name}
        </button>
      ) : !persona.name && !asking && !editing ? (
        <Button size="sm" onClick={() => setEditing(true)}>
          Add your name
        </Button>
      ) : (
        <>
          {asking ? (
            <span className="text-muted-foreground">Enter your name to record changes.</span>
          ) : null}
          <NameForm
            initial={persona.name}
            onDone={(name) => {
              setPersona({ ...persona, name });
              setEditing(false);
            }}
          />
        </>
      )}
    </div>
  );
}
