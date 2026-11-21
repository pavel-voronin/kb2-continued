unit KBSave;
{ Сохраняет прежний формат KB2.DAT: флаги упакованы побитово. }
{$G+,R-,S-,I+,A+}

interface

uses KBState;

const
  LegacyFlagBytes = SizeOf(TCampaignFlags);
  LegacyDataBytes = SizeOf(TCampaignState) - LegacyFlagBytes;
  LegacyDataWords = LegacyDataBytes div 2;
  LegacyPackedBytes = (LegacyFlagBytes + 7) div 8;
  LegacySaveBytes = LegacyPackedBytes + LegacyDataBytes;

procedure PrepareSave;
function WriteCampaign(StripRoamers: boolean): boolean;
procedure ReadCampaign;

implementation

uses KBTables, KBFiles;

procedure PrepareSave;
var
  I: byte;

begin
  Game.Campaign.ArchivedIsland := Game.Campaign.Island;
  Game.Campaign.ArchiveMarker := 0;

  for I := 25 to 29 do Game.Campaign.Mutants[I] := CreatureDefinitions[I];
end;

function WriteCampaign(StripRoamers: boolean): boolean;
var
  Written: boolean;
  WizardCell, MageCell: word;

function SavedCell(X, Y: byte): word;
begin
  SavedCell := LegacyPackedBytes + Ofs(Game.Campaign.Map[Game.Campaign.Island, X, Y]) -
    Ofs(Game.Campaign.VisitedCastles);
end;

begin
  Written := false;
  if StripRoamers then
  begin
    WizardCell := SavedCell(Game.World.WizardPosition.X, Game.World.WizardPosition.Y);
    MageCell := SavedCell(Game.World.MagePosition.X, Game.World.MagePosition.Y);
  end;
  asm
    lea si, Game.Campaign.Flags.Discovery
    lea di, Game.Runtime.PictureBanks
    add di, 16
    mov ax, [di]
    mov bx, [di+2]
    mov es, bx
    mov di, ax
    push di
    mov cx, LegacyFlagBytes
    xor bh, bh
    inc bh
    xor ah, ah

@Pack:
    lodsb
    or al, al
    je @Empty
    or ah, bh

@Empty:
    rol bh, 1
    jnc @Next
    mov al, ah
    xor ah, ah
    stosb

@Next:
    loop @Pack
    mov al, ah
    stosb
    lea si, Game.Campaign.VisitedCastles
    mov cx, LegacyDataWords
    rep movsw

    cmp StripRoamers, 0
    je @CreateFile
    mov bx, di
    sub bx, LegacySaveBytes
    add bx, WizardCell
    mov byte ptr es:[bx], 0
    mov bx, di
    sub bx, LegacySaveBytes
    add bx, MageCell
    mov byte ptr es:[bx], 0

@CreateFile:
    lea dx, Game.Runtime.DataFileName
    mov bx, dx
    inc dx
    mov al, [bx]
    xor ah, ah
    add bx, ax
    inc bx
    mov al, 0
    mov [bx], al
    xor cx, cx
    mov ah, 3ch
    int 21h
    mov cx, di
    pop di
    jc @Finished
    mov bx, ax
    sub cx, di
    mov dx, di
    push ds
    mov ax, es
    mov ds, ax
    mov ah, 40h
    push cx
    int 21h
    pop cx
    jc @Close
    cmp ax, cx
    jne @Close
    mov Written, 1

@Close:
    mov ah, 3eh
    int 21h
    pop ds
    jnc @Finished
    mov Written, 0

@Finished:
  end;

  WriteCampaign := Written;

  LoadResourceFile(Game.Runtime.PictureBanks[4], Game.Runtime.IslandPictureFileName);
end;

procedure ReadCampaign;
begin
  asm
    mov ax, ds
    mov es, ax
    lea dx, Game.Runtime.DataFileName
    mov bx, dx
    inc dx
    mov al, [bx]
    xor ah, ah
    add bx, ax
    inc bx
    mov al, 0
    mov [bx], al
    mov ax, 3d00h
    int 21h
    jc @Finished
    mov bx, ax
    xor cx, cx
    xor dx, dx
    mov ax, 4202h
    int 21h
    mov si, ax
    mov ax, 4200h
    int 21h
    lea di, Game.Runtime.PictureBanks
    mov dx, [di]
    mov cx, [di+2]
    mov ds, cx
    mov ah, 3fh
    mov cx, si
    int 21h
    mov ah, 3eh
    int 21h
    mov si, dx
    lea di, Game.Campaign.Flags.Discovery
    mov cx, LegacyFlagBytes
    inc cx
    xor bh, bh
    inc bh
    jmp @ReadPacked

@Unpack:
    xor ah, ah
    test al, bh
    je @Store
    inc ah

@Store:
    mov es:[di], ah
    inc di
    rol bh, 1
    jnc @Continue

@ReadPacked:
    lodsb

@Continue:
    loop @Unpack
    lea di, Game.Campaign.VisitedCastles
    mov cx, LegacyDataWords
    rep movsw
    mov ax, es
    mov ds, ax

@Finished:
  end;
end;

end.
