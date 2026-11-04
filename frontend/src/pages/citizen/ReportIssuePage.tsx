import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { 
  FileText, Camera, MapPin, CheckCircle2, ArrowRight, ArrowLeft, 
  AlertCircle, ShieldCheck, Sparkles, Loader2 
} from 'lucide-react';
import { complaintsService } from '../../services/complaintsService';
import { ComplaintCategory, Complaint } from '../../types';
import { Button } from '../../components/common/Button';
import { FileUpload } from '../../components/common/FileUpload';
import { MapPicker } from '../../components/common/MapPicker';
import { useToast } from '../../context/ToastContext';

export const ReportIssuePage: React.FC = () => {
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<ComplaintCategory>('ROADS');
  const [subcategory, setSubcategory] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  // Default coordinates (Hyderabad center)
  const [latitude, setLatitude] = useState<number>(17.4399);
  const [longitude, setLongitude] = useState<number>(78.4983);
  const [address, setAddress] = useState('');
  const [landmark, setLandmark] = useState('');

  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittedComplaint, setSubmittedComplaint] = useState<Complaint | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { success, error: toastError } = useToast();
  const navigate = useNavigate();

  const handleNext = () => {
    setError(null);
    if (currentStep === 1) {
      if (title.trim().length < 5) {
        setError('Please provide a descriptive title (at least 5 characters).');
        return;
      }
      if (description.trim().length < 10) {
        setError('Please describe the issue in more detail (at least 10 characters).');
        return;
      }
    }
    if (currentStep === 3) {
      if (!latitude || !longitude) {
        setError('Please select an issue location on the map.');
        return;
      }
    }
    setCurrentStep((prev) => prev + 1);
  };

  const handleBack = () => {
    setError(null);
    setCurrentStep((prev) => prev - 1);
  };

  const handleSubmit = async () => {
    if (!privacyConsent) {
      setError('Please check the consent box to confirm report veracity.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // 1. Create complaint record in PostgreSQL
      const complaint = await complaintsService.createComplaint({
        title,
        description,
        category,
        subcategory: subcategory || undefined,
        latitude,
        longitude,
        address: address || undefined,
        landmark: landmark || undefined,
      });

      // 2. Upload photo attachment if selected
      if (selectedFile) {
        try {
          await complaintsService.uploadAttachment(complaint.id, selectedFile, 'ORIGINAL');
        } catch {
          // Photo upload warning without failing ticket
        }
      }

      success('Complaint Submitted Successfully', `Reference: #${complaint.reference_number}`);
      setSubmittedComplaint(complaint);
    } catch (err: any) {
      setError(err.message || 'Failed to submit complaint. Please check your connection.');
      toastError('Submission Failed', err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (submittedComplaint) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-sm text-center space-y-6">
          <div className="w-16 h-16 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-10 h-10" />
          </div>

          <div className="space-y-2">
            <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Report Registered</span>
            <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              Complaint #{submittedComplaint.reference_number}
            </h2>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              Your civic report has been securely saved in the municipal registry. Automated AI triage has analyzed the report and scheduled initial operational review.
            </p>
          </div>

          <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-left text-xs space-y-2">
            <div className="flex justify-between">
              <span className="text-slate-500">Title:</span>
              <span className="font-semibold text-slate-800">{submittedComplaint.title}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Category:</span>
              <span className="font-semibold text-slate-800">{submittedComplaint.category}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Status:</span>
              <span className="font-semibold text-brand-700">{submittedComplaint.status}</span>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
            <Link
              to={`/citizen/complaints/${submittedComplaint.id}`}
              className="px-6 py-3 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-semibold shadow-xs transition"
            >
              Track Complaint Progress
            </Link>
            <Link
              to="/citizen"
              className="px-6 py-3 bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 rounded-xl text-xs font-semibold shadow-xs transition"
            >
              Return to Citizen Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-12 space-y-8">
      {/* Step Indicator Header */}
      <div>
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">New Civic Report</span>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Report a Civic Hazard</h1>
        
        {/* Step Indicator Bar */}
        <div className="flex items-center justify-between mt-6 max-w-lg">
          {[
            { step: 1, title: 'Details', icon: FileText },
            { step: 2, title: 'Evidence', icon: Camera },
            { step: 3, title: 'Location', icon: MapPin },
            { step: 4, title: 'Review', icon: CheckCircle2 },
          ].map(({ step, title, icon: Icon }) => (
            <div key={step} className="flex flex-col items-center">
              <div
                className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold text-xs transition-all ${
                  currentStep === step
                    ? 'bg-brand-600 text-white shadow-sm ring-4 ring-brand-100'
                    : currentStep > step
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-100 text-slate-400'
                }`}
              >
                {currentStep > step ? <CheckCircle2 className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
              </div>
              <span className={`text-[11px] font-semibold mt-1.5 ${currentStep === step ? 'text-brand-600' : 'text-slate-400'}`}>
                {title}
              </span>
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Wizard Step Content */}
      <div className="bg-white p-7 sm:p-9 rounded-3xl border border-slate-200 shadow-xs space-y-6">
        {/* STEP 1: Details */}
        {currentStep === 1 && (
          <div className="space-y-4">
            <h3 className="text-base font-bold text-slate-900">Step 1: Describe the Civic Issue</h3>
            
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Complaint Title *
              </label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Deep pothole on 4th Main road causing vehicular skidding"
                className="w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Primary Category *
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value as ComplaintCategory)}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
                >
                  <option value="ROADS">Potholes and Damaged Roads</option>
                  <option value="STREETLIGHTS">Broken Streetlights & Electrical</option>
                  <option value="GARBAGE">Garbage & Illegal Dumping</option>
                  <option value="DRAINAGE">Drainage & Waterlogging</option>
                  <option value="WATER_SUPPLY">Water Supply & Pipeline Leakage</option>
                  <option value="FOOTPATHS">Damaged Footpaths & Walkways</option>
                  <option value="TREES_HAZARDS">Fallen Trees & Public Hazards</option>
                  <option value="SANITATION">Public Sanitation Issues</option>
                  <option value="OTHER">Other Civic Complaint</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Subcategory (Optional)
                </label>
                <input
                  type="text"
                  value={subcategory}
                  onChange={(e) => setSubcategory(e.target.value)}
                  placeholder="e.g. Broken luminaire, open manhole"
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Detailed Description *
              </label>
              <textarea
                required
                rows={5}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Explain the defect location, severity, when it started, and potential safety hazards to pedestrians or vehicles..."
                className="w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>
        )}

        {/* STEP 2: Evidence */}
        {currentStep === 2 && (
          <div className="space-y-4">
            <h3 className="text-base font-bold text-slate-900">Step 2: Upload Photographic Evidence</h3>
            <p className="text-xs text-slate-500">
              Clear photos enable our computer vision AI to assess defect depth, verify damage severity, and speed up work order dispatch.
            </p>

            <FileUpload
              selectedFile={selectedFile}
              onFileSelect={setSelectedFile}
              maxSizeMB={10}
            />

            <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-blue-900 text-xs flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-ai-600 flex-shrink-0" />
              <span>AI Vision will inspect this image to detect surface deformities and confirm hazard legitimacy.</span>
            </div>
          </div>
        )}

        {/* STEP 3: Location */}
        {currentStep === 3 && (
          <div className="space-y-4">
            <h3 className="text-base font-bold text-slate-900">Step 3: Pinpoint the Issue Location</h3>
            <p className="text-xs text-slate-500">
              Pinpoint the defect on our interactive map, use your device GPS, or enter manual coordinates below.
            </p>

            <MapPicker
              latitude={latitude}
              longitude={longitude}
              onChange={(lat, lon, addressSuggestion) => {
                setLatitude(lat);
                setLongitude(lon);
                if (addressSuggestion && !address.trim()) {
                  setAddress(addressSuggestion);
                }
              }}
              height="300px"
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Street Address / Area
                </label>
                <input
                  type="text"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="e.g. 5th Cross Road, Ward 14"
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Nearby Landmark (Optional)
                </label>
                <input
                  type="text"
                  value={landmark}
                  onChange={(e) => setLandmark(e.target.value)}
                  placeholder="e.g. Opposite Metro Pillar 42"
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>
          </div>
        )}

        {/* STEP 4: Review & Submit */}
        {currentStep === 4 && (
          <div className="space-y-6">
            <h3 className="text-base font-bold text-slate-900">Step 4: Review Your Report</h3>
            
            <div className="bg-slate-50 p-5 rounded-2xl border border-slate-200 text-xs space-y-3">
              <div className="flex justify-between border-b border-slate-200 pb-2">
                <span className="text-slate-500">Title:</span>
                <span className="font-bold text-slate-900">{title}</span>
              </div>
              <div className="flex justify-between border-b border-slate-200 pb-2">
                <span className="text-slate-500">Category:</span>
                <span className="font-semibold text-brand-700">{category}</span>
              </div>
              <div className="border-b border-slate-200 pb-2">
                <span className="text-slate-500 block mb-1">Description:</span>
                <p className="text-slate-700 leading-relaxed">{description}</p>
              </div>
              <div className="flex justify-between border-b border-slate-200 pb-2">
                <span className="text-slate-500">Location Coordinates:</span>
                <span className="font-mono text-slate-700">{latitude.toFixed(5)}, {longitude.toFixed(5)}</span>
              </div>
              {address && (
                <div className="flex justify-between border-b border-slate-200 pb-2">
                  <span className="text-slate-500">Address / Landmark:</span>
                  <span className="text-slate-800">{address} {landmark ? `(${landmark})` : ''}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-500">Photo Attached:</span>
                <span className="font-semibold text-slate-800">{selectedFile ? selectedFile.name : 'None provided'}</span>
              </div>
            </div>

            {/* Privacy and Verification Consent */}
            <div className="flex items-start gap-3 p-3.5 bg-brand-50/60 border border-brand-200 rounded-2xl">
              <input
                type="checkbox"
                id="consent"
                checked={privacyConsent}
                onChange={(e) => setPrivacyConsent(e.target.checked)}
                className="mt-0.5 w-4 h-4 text-brand-600 rounded border-slate-300 focus:ring-brand-500 cursor-pointer"
              />
              <label htmlFor="consent" className="text-xs text-slate-700 cursor-pointer leading-relaxed">
                I certify that this complaint reflects a genuine civic infrastructure defect. I understand my report will undergo automated AI assessment and spatial duplicate verification before dispatch to municipal field crews.
              </label>
            </div>
          </div>
        )}

        {/* Wizard Controls */}
        <div className="flex items-center justify-between pt-4 border-t border-slate-100">
          {currentStep > 1 ? (
            <Button
              type="button"
              variant="outline"
              size="md"
              onClick={handleBack}
              icon={<ArrowLeft className="w-4 h-4" />}
            >
              Previous
            </Button>
          ) : (
            <div></div>
          )}

          {currentStep < 4 ? (
            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={handleNext}
              icon={<ArrowRight className="w-4 h-4" />}
            >
              Continue
            </Button>
          ) : (
            <Button
              type="button"
              variant="primary"
              size="md"
              isLoading={submitting}
              onClick={handleSubmit}
              icon={<CheckCircle2 className="w-4 h-4" />}
            >
              Submit Report
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

