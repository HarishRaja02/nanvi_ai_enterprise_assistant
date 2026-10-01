import { FONT_SCALE_STEPS, type FontScale } from "../../hooks/useFontScale";

type Props = {
  fontScale: FontScale;
  onChange: (scale: FontScale) => void;
};

export function DisplaySettings({ fontScale, onChange }: Props) {
  const scaleIndex = FONT_SCALE_STEPS.indexOf(fontScale);

  return (
    <section className="display-settings" aria-labelledby="display-settings-title">
      <div>
        <h2 id="display-settings-title">Text size</h2>
        <p>Make text easier to read across Nanvi. Your choice is saved on this device.</p>
      </div>

      <div className="display-settings-control">
        <button
          type="button"
          className="account-secondary-action"
          onClick={() => onChange(FONT_SCALE_STEPS[Math.max(0, scaleIndex - 1)])}
          disabled={scaleIndex === 0}
          aria-label="Decrease text size"
        >
          A−
        </button>
        <output className="display-settings-value" aria-live="polite">
          {Math.round(fontScale * 100)}%
        </output>
        <button
          type="button"
          className="account-secondary-action"
          onClick={() => onChange(FONT_SCALE_STEPS[Math.min(FONT_SCALE_STEPS.length - 1, scaleIndex + 1)])}
          disabled={scaleIndex === FONT_SCALE_STEPS.length - 1}
          aria-label="Increase text size"
        >
          A+
        </button>
        <button
          type="button"
          className="account-secondary-action"
          onClick={() => onChange(1)}
          disabled={fontScale === 1}
        >
          Reset
        </button>
      </div>
    </section>
  );
}
