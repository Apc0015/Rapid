import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import '../rapid-design.css';
import '../product-shell.css';
import './react-app.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
