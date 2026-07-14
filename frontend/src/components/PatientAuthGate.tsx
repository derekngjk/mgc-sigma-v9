import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPatientToken } from '../lib/patientSession';

interface PatientAuthGateProps {
  children: React.ReactNode;
}

// Guards the patient account routes. A missing token bounces to /patient/login;
// an expired token surfaces as a 401 from the API, which the pages handle by
// clearing the token and redirecting here.
export function PatientAuthGate({ children }: PatientAuthGateProps) {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getPatientToken()) {
      navigate('/patient/login', { replace: true });
      return;
    }
    setReady(true);
  }, [navigate]);

  if (!ready) return null;
  return <>{children}</>;
}
