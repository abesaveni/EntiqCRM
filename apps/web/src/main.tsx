import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { Toaster } from '@entiq/ui/sonner';
import { router } from './routes';
import './styles/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
    <Toaster position="bottom-right" richColors closeButton />
  </React.StrictMode>,
);
