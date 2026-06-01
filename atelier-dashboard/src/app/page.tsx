import StitchClientShell from '../components/StitchClientShell';
import ErrorBoundary from '../components/ErrorBoundary';

export default function Home() {
  return (
    <ErrorBoundary>
      <StitchClientShell />
    </ErrorBoundary>
  );
}
