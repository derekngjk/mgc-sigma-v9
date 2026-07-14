import { useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ReportView } from '../components/ReportView';
import type { Lang, ReportData } from '../components/ReportView';
import { clearPatientToken, patientFetch } from '../lib/patientSession';

export default function PatientReportPage() {
  const { commId } = useParams<{ commId: string }>();
  const navigate = useNavigate();

  const handleUnauthorized = useCallback(() => {
    clearPatientToken();
    navigate('/patient/login', { replace: true });
  }, [navigate]);

  const loadReport = useCallback(
    async (lang: Lang): Promise<ReportData> => {
      const res = await patientFetch(`/api/account/reports/${commId}?lang=${lang}`);
      if (res.status === 401) {
        handleUnauthorized();
        throw new Error('Session expired');
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as ReportData;
    },
    [commId, handleUnauthorized],
  );

  const loadAudio = useCallback(
    async (lang: Lang): Promise<{ url: string; sentences: string[] }> => {
      const res = await patientFetch(`/api/account/reports/${commId}/audio?lang=${lang}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as { url: string; sentences: string[] };
    },
    [commId],
  );

  return (
    <ReportView
      loadReport={loadReport}
      loadAudio={loadAudio}
      onBack={() => navigate('/patient')}
    />
  );
}
