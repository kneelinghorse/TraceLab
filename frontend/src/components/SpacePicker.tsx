/**
 * Where a new project lives (PERSONAL-2, decision #533).
 *
 * Shown only when the caller has more than one Space. The default is their personal
 * Space, labelled "My Space", and is represented by an empty value so the create
 * call sends no workspace_id and the server places the project exactly as it would
 * without a picker. With one Space, while loading, or on error, nothing renders.
 */

import useSWR from "swr";

import { useAuth } from "@/contexts/AuthContext";
import { spacesApi } from "@/lib/api/spaces";

type SpacePickerProps = {
  value: string;
  onChange: (spaceId: string) => void;
  className?: string;
  // Each form keeps its own field styling.
  labelClassName?: string;
  selectClassName?: string;
};

export function SpacePicker({
  value,
  onChange,
  className,
  labelClassName = "form-label",
  selectClassName = "form-input",
}: SpacePickerProps) {
  const { user } = useAuth();
  const spaces = useSWR(user ? ["spaces", user.user_id] : null, () => spacesApi.list());
  const own = spaces.data?.find((space) => space.personal_owner_id === user?.user_id);
  if (!spaces.data || spaces.data.length < 2 || !own) {
    return null;
  }
  const others = spaces.data.filter((space) => space.id !== own.id);

  return (
    <div className={className}>
      <label htmlFor="new-project-space" className={labelClassName}>
        Space
      </label>
      <select
        id="new-project-space"
        className={selectClassName}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">My Space</option>
        {others.map((space) => (
          <option key={space.id} value={space.id}>
            {space.name}
          </option>
        ))}
      </select>
      <p className="mt-1 text-xs text-muted">Everyone in a shared Space can see its projects.</p>
    </div>
  );
}
