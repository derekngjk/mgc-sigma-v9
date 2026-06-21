import { useState } from 'react';
import { supabase } from '../lib/supabase';

type Stage = 'idle' | 'sending' | 'sent';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [stage, setStage] = useState<Stage>('idle');
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStage('sending');
    setError(null);

    const { error: authError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/clinician`,
      },
    });

    if (authError) {
      setError(authError.message);
      setStage('idle');
    } else {
      setStage('sent');
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
            Sigma Tech · Clinician Portal
          </p>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">Sign in</h1>
        </div>

        {stage === 'sent' ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            Check your email — we sent a magic link to <strong>{email}</strong>.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="mb-1 block text-sm font-medium text-slate-700"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="clinician@hospital.sg"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600">{error}</p>
            )}

            <button
              type="submit"
              disabled={stage === 'sending'}
              className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {stage === 'sending' ? 'Sending…' : 'Send magic link'}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-xs text-slate-400">
          PoC environment · Synthetic data only
        </p>
      </div>
    </div>
  );
}
