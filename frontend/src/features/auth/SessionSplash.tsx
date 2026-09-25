import { LOGO_URL } from "../../lib/config";

/** Shown only while the stored session is being verified with the backend. */
export function SessionSplash({ title, detail }: { title: string; detail: string }) {
  return (
    <main className="fullscreen">
      <section className="splash" role="status">
        <img src={LOGO_URL} alt="Nanvi" className="brand-logo-img splash-logo" />
        <div className="spinner spinner-lg" aria-hidden="true" />
        <h1>{title}</h1>
        <p>{detail}</p>
      </section>
    </main>
  );
}
