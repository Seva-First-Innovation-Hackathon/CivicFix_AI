import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { 
  ShieldCheck, MapPin, Bell, Globe, LogOut, User as UserIcon, 
  Menu, X, PlusCircle, LayoutDashboard, Layers, ShieldAlert 
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../i18n/LanguageContext';
import { Language } from '../../i18n/translations';

export const Navbar: React.FC = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const { language, setLanguage, t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [langMenuOpen, setLangMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const isMunicipalStaff = user && ['GOVERNMENT_ADMIN', 'MUNICIPAL_MEMBER', 'FIELD_CREW'].includes(user.role);

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200">
      {/* Demo mode top banner */}
      <div className="bg-gradient-to-r from-brand-900 via-brand-800 to-ai-700 text-white text-xs py-1.5 px-4 text-center font-medium tracking-wide flex items-center justify-center gap-2">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
        <span>{t('demo_mode_banner')}</span>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl bg-brand-600 text-white flex items-center justify-center shadow-md shadow-brand-500/20 group-hover:bg-brand-700 transition">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xl font-bold text-brand-950 tracking-tight flex items-center gap-1.5">
                CivicFix <span className="text-ai-600 text-xs px-1.5 py-0.5 rounded bg-ai-50 border border-ai-200">AI</span>
              </span>
              <p className="text-[10px] text-slate-500 font-medium tracking-wider uppercase -mt-0.5">
                Report • Resolve • Trust
              </p>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center space-x-6 text-sm font-medium text-slate-600">
            <Link to="/" className={`hover:text-brand-600 transition ${location.pathname === '/' ? 'text-brand-600 font-semibold' : ''}`}>
              Home
            </Link>
            <Link to="/how-it-works" className={`hover:text-brand-600 transition ${location.pathname === '/how-it-works' ? 'text-brand-600 font-semibold' : ''}`}>
              {t('how_it_works')}
            </Link>
            <Link to="/impact" className={`hover:text-brand-600 transition ${location.pathname === '/impact' ? 'text-brand-600 font-semibold' : ''}`}>
              {t('public_dashboard')}
            </Link>
            <Link to="/categories" className={`hover:text-brand-600 transition ${location.pathname === '/categories' ? 'text-brand-600 font-semibold' : ''}`}>
              {t('categories')}
            </Link>

            {/* Portal Direct Links */}
            {isAuthenticated && !isMunicipalStaff && (
              <>
                <Link to="/citizen" className={`hover:text-brand-600 transition ${location.pathname === '/citizen' ? 'text-brand-600 font-semibold' : ''}`}>
                  Dashboard
                </Link>
                <Link to="/citizen/complaints" className={`hover:text-brand-600 transition ${location.pathname.startsWith('/citizen/complaints') ? 'text-brand-600 font-semibold' : ''}`}>
                  My Reports
                </Link>
              </>
            )}

            {isAuthenticated && isMunicipalStaff && (
              <Link to="/admin" className="text-ai-700 font-semibold flex items-center gap-1.5 bg-ai-50 px-3 py-1.5 rounded-lg border border-ai-200 hover:bg-ai-100 transition">
                <LayoutDashboard className="w-4 h-4" />
                Command Portal
              </Link>
            )}
          </nav>

          {/* Right Header Action Items */}
          <div className="hidden md:flex items-center space-x-3">
            {/* Language Selector */}
            <div className="relative">
              <button
                onClick={() => setLangMenuOpen(!langMenuOpen)}
                className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 px-2.5 py-1.5 rounded-lg transition"
              >
                <Globe className="w-3.5 h-3.5" />
                <span className="uppercase">{language}</span>
              </button>

              {langMenuOpen && (
                <div className="absolute right-0 mt-2 w-32 bg-white rounded-xl shadow-xl border border-slate-200 py-1 z-50">
                  <button
                    onClick={() => { setLanguage('en'); setLangMenuOpen(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs font-medium hover:bg-slate-50 ${language === 'en' ? 'text-brand-600 font-bold bg-brand-50' : 'text-slate-700'}`}
                  >
                    English (EN)
                  </button>
                  <button
                    onClick={() => { setLanguage('te'); setLangMenuOpen(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs font-medium hover:bg-slate-50 ${language === 'te' ? 'text-brand-600 font-bold bg-brand-50' : 'text-slate-700'}`}
                  >
                    తెలుగు (TE)
                  </button>
                  <button
                    onClick={() => { setLanguage('hi'); setLangMenuOpen(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs font-medium hover:bg-slate-50 ${language === 'hi' ? 'text-brand-600 font-bold bg-brand-50' : 'text-slate-700'}`}
                  >
                    हिन्दी (HI)
                  </button>
                </div>
              )}
            </div>

            {/* Authenticated State */}
            {isAuthenticated ? (
              <div className="flex items-center space-x-3">
                {!isMunicipalStaff && (
                  <Link
                    to="/citizen/report"
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold shadow-sm transition"
                  >
                    <PlusCircle className="w-4 h-4" />
                    {t('report_issue')}
                  </Link>
                )}

                <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
                  <div className="text-right">
                    <p className="text-xs font-bold text-slate-800 leading-tight">{user?.full_name}</p>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      {user?.role.replace('_', ' ')}
                    </span>
                  </div>
                  <button
                    onClick={handleLogout}
                    title="Sign Out"
                    className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : (
              /* Unauthenticated Actions */
              <div className="flex items-center space-x-2">
                <Link
                  to="/login"
                  className="px-3 py-1.5 text-xs font-semibold text-slate-700 hover:text-brand-600 transition"
                >
                  Citizen Login
                </Link>
                <Link
                  to="/register"
                  className="px-3.5 py-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition"
                >
                  Register
                </Link>
                <Link
                  to="/staff/login"
                  className="px-2.5 py-1.5 text-[11px] font-semibold text-slate-500 hover:text-slate-800 border border-slate-200 hover:bg-slate-50 rounded-lg transition"
                >
                  Staff Portal
                </Link>
              </div>
            )}
          </div>

          {/* Mobile menu button */}
          <div className="flex md:hidden items-center gap-2">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 focus:outline-none"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-slate-200 bg-white px-4 pt-2 pb-4 space-y-3 shadow-lg">
          <Link to="/" onClick={() => setMobileMenuOpen(false)} className="block py-2 text-sm font-medium text-slate-700">
            Home
          </Link>
          <Link to="/how-it-works" onClick={() => setMobileMenuOpen(false)} className="block py-2 text-sm font-medium text-slate-700">
            {t('how_it_works')}
          </Link>
          <Link to="/impact" onClick={() => setMobileMenuOpen(false)} className="block py-2 text-sm font-medium text-slate-700">
            {t('public_dashboard')}
          </Link>
          <Link to="/categories" onClick={() => setMobileMenuOpen(false)} className="block py-2 text-sm font-medium text-slate-700">
            {t('categories')}
          </Link>

          {isAuthenticated ? (
            <div className="pt-3 border-t border-slate-200 space-y-2">
              <p className="text-xs text-slate-500">Signed in as {user?.full_name}</p>
              {!isMunicipalStaff ? (
                <>
                  <Link to="/citizen" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-sm font-semibold text-brand-600">
                    Citizen Dashboard
                  </Link>
                  <Link to="/citizen/report" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-sm font-semibold text-brand-600">
                    + Report an Issue
                  </Link>
                </>
              ) : (
                <Link to="/admin" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-sm font-semibold text-ai-700">
                  Municipal Command Portal
                </Link>
              )}
              <button onClick={handleLogout} className="w-full text-left py-1.5 text-sm font-semibold text-rose-600">
                Sign Out
              </button>
            </div>
          ) : (
            <div className="pt-3 border-t border-slate-200 flex flex-col gap-2">
              <Link to="/login" onClick={() => setMobileMenuOpen(false)} className="text-center py-2 text-sm font-semibold text-slate-700 border border-slate-200 rounded-lg">
                Citizen Login
              </Link>
              <Link to="/register" onClick={() => setMobileMenuOpen(false)} className="text-center py-2 text-sm font-semibold text-white bg-brand-600 rounded-lg">
                Register as Citizen
              </Link>
              <Link to="/staff/login" onClick={() => setMobileMenuOpen(false)} className="text-center py-2 text-xs font-medium text-slate-500">
                Municipal Staff Portal
              </Link>
            </div>
          )}
        </div>
      )}
    </header>
  );
};

