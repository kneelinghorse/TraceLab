import { useCallback } from "react";

interface DynamicListInputProps {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
  placeholder?: string;
  minItems?: number;
  error?: string;
  required?: boolean;
}

/**
 * A reusable component for managing a dynamic list of string items.
 * Supports adding, removing, and editing items.
 */
export function DynamicListInput({
  label,
  items,
  onChange,
  placeholder = "Enter item...",
  minItems = 1,
  error,
  required = false,
}: DynamicListInputProps) {
  const handleAdd = useCallback(() => {
    onChange([...items, ""]);
  }, [items, onChange]);

  const handleRemove = useCallback(
    (index: number) => {
      if (items.length <= minItems) return;
      const updated = items.filter((_, i) => i !== index);
      onChange(updated);
    },
    [items, minItems, onChange]
  );

  const handleChange = useCallback(
    (index: number, value: string) => {
      const updated = items.map((item, i) => (i === index ? value : item));
      onChange(updated);
    },
    [items, onChange]
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="form-label">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
        <button
          type="button"
          onClick={handleAdd}
          className="text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
        >
          + Add Item
        </button>
      </div>

      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index} className="flex gap-2">
            <input
              type="text"
              value={item}
              onChange={(e) => handleChange(index, e.target.value)}
              placeholder={placeholder}
              className="form-input flex-1"
            />
            {items.length > minItems && (
              <button
                type="button"
                onClick={() => handleRemove(index)}
                className="px-3 py-2 text-sm font-medium text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
                aria-label={`Remove item ${index + 1}`}
              >
                Remove
              </button>
            )}
          </div>
        ))}
      </div>

      {error && <p className="form-error">{error}</p>}
    </div>
  );
}
