import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: "",
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      message: error.message || "Bilinmeyen bir render hatası oluştu.",
    };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Frontend render hatası", error, info);
  }

  override render() {
    if (this.state.hasError) {
      return (
        <div className="startup-screen">
          <div className="startup-card error-card">
            <h1>Arayüz Hatası</h1>
            <p>Uygulama görünümü yüklenirken beklenmeyen bir hata oluştu.</p>
            <p>{this.state.message}</p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
