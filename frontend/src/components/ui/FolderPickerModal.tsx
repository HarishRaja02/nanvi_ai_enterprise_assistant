import { Modal } from "./Modal";
import { CompanyFolderPicker } from "./CompanyFolderPicker";
import type { NanviApiClient } from "../../api";

type Props = {
  api: NanviApiClient;
  open: boolean;
  onClose: () => void;
};

export function FolderPickerModal({ api, open, onClose }: Props) {
  if (!open) return null;

  return (
    <Modal title="Company Data Folder" onClose={onClose}>
      <div className="folder-picker-modal-content">
        <CompanyFolderPicker api={api} />
      </div>
    </Modal>
  );
}
