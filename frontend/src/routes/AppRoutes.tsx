import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import { AdminLayout } from '../components/layout/AdminLayout';
import { RequireCitizen, RequireMunicipalStaff, RequireGovernmentAdmin } from './Guards';

// Public Pages
import { HomePage } from '../pages/public/HomePage';
import { AboutPage } from '../pages/public/AboutPage';
import { HowItWorksPage } from '../pages/public/HowItWorksPage';
import { CategoriesPage } from '../pages/public/CategoriesPage';
import { ImpactDashboardPage } from '../pages/public/ImpactDashboardPage';
import { ContactPage } from '../pages/public/ContactPage';
import { CitizenLoginPage } from '../pages/public/CitizenLoginPage';
import { CitizenRegisterPage } from '../pages/public/CitizenRegisterPage';
import { StaffLoginPage } from '../pages/public/StaffLoginPage';
import { PrivacyPolicyPage } from '../pages/public/PrivacyPolicyPage';
import { TermsPage } from '../pages/public/TermsPage';
import { AccessibilityPage, NotFoundPage } from '../pages/public/AccessibilityPage';

// Citizen Pages
import { CitizenDashboard } from '../pages/citizen/CitizenDashboard';
import { ReportIssuePage } from '../pages/citizen/ReportIssuePage';
import { MyComplaintsPage } from '../pages/citizen/MyComplaintsPage';
import { ComplaintDetailsPage } from '../pages/citizen/ComplaintDetailsPage';

// Municipal Command Pages
import { AdminDashboard } from '../pages/admin/AdminDashboard';
import { AdminComplaintsPage } from '../pages/admin/AdminComplaintsPage';
import { AdminComplaintDetailPage } from '../pages/admin/AdminComplaintDetailPage';
import { LiveIssueMapPage } from '../pages/admin/LiveIssueMapPage';
import { WorkOrdersPage } from '../pages/admin/WorkOrdersPage';
import { CrewTasksPage } from '../pages/admin/CrewTasksPage';
import { DepartmentsPage } from '../pages/admin/DepartmentsPage';
import { UsersManagementPage } from '../pages/admin/UsersManagementPage';
import { DuplicatesPage } from '../pages/admin/DuplicatesPage';
import { AnalyticsReportsPage } from '../pages/admin/AnalyticsReportsPage';
import { AuditLogsPage } from '../pages/admin/AuditLogsPage';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public & Citizen Layout Routes */}
      <Route element={<AppLayout />}>
        {/* Public Routes */}
        <Route path="/" element={<HomePage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/how-it-works" element={<HowItWorksPage />} />
        <Route path="/categories" element={<CategoriesPage />} />
        <Route path="/impact" element={<ImpactDashboardPage />} />
        <Route path="/contact" element={<ContactPage />} />
        <Route path="/login" element={<CitizenLoginPage />} />
        <Route path="/register" element={<CitizenRegisterPage />} />
        <Route path="/staff/login" element={<StaffLoginPage />} />
        <Route path="/privacy" element={<PrivacyPolicyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/accessibility" element={<AccessibilityPage />} />

        {/* Citizen Portal (Protected) */}
        <Route
          path="/citizen"
          element={
            <RequireCitizen>
              <CitizenDashboard />
            </RequireCitizen>
          }
        />
        <Route
          path="/citizen/report"
          element={
            <RequireCitizen>
              <ReportIssuePage />
            </RequireCitizen>
          }
        />
        <Route
          path="/citizen/complaints"
          element={
            <RequireCitizen>
              <MyComplaintsPage />
            </RequireCitizen>
          }
        />
        <Route
          path="/citizen/complaints/:id"
          element={
            <RequireCitizen>
              <ComplaintDetailsPage />
            </RequireCitizen>
          }
        />

        {/* 404 Catch-all */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      {/* Municipal Command Portal (Protected) */}
      <Route
        path="/admin"
        element={
          <RequireMunicipalStaff>
            <AdminLayout />
          </RequireMunicipalStaff>
        }
      >
        <Route index element={<AdminDashboard />} />
        <Route path="complaints" element={<AdminComplaintsPage />} />
        <Route path="complaints/:id" element={<AdminComplaintDetailPage />} />
        <Route path="map" element={<LiveIssueMapPage />} />
        <Route path="work-orders" element={<WorkOrdersPage />} />
        <Route path="crew-tasks" element={<CrewTasksPage />} />
        <Route path="departments" element={<DepartmentsPage />} />
        <Route path="duplicates" element={<DuplicatesPage />} />
        <Route path="analytics" element={<AnalyticsReportsPage />} />

        {/* Government Admin Only */}
        <Route
          path="users"
          element={
            <RequireGovernmentAdmin>
              <UsersManagementPage />
            </RequireGovernmentAdmin>
          }
        />
        <Route
          path="audit-logs"
          element={
            <RequireGovernmentAdmin>
              <AuditLogsPage />
            </RequireGovernmentAdmin>
          }
        />
      </Route>
    </Routes>
  );
};

