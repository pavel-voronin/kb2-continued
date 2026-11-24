unit KBVisit;
{$G+,R-,S-,I+,A+}

interface

procedure TreasureVisit;
procedure UndergroundVisit;
function FindWanderingArmy(Island, X, Y: byte): shortint;
procedure WanderingArmyVisit;
procedure BoardShip;
procedure SandLanding;
procedure RitualGuardianVisit;
procedure RegrowMountain;

implementation

uses KBAdvent, KBBattle, KBSess, KBHud, KBReport, KBTables, KBUI, KBGfx, KBInput, KBSound, Crt, KBTypes, KBState;

procedure TreasureVisit;
begin
  EncounterLanding;
  Game.Campaign.Map[Game.Campaign.Island, Game.World.GenerationX, Game.World.GenerationY] := 0;
  Game.World.GenerationCount := Random(IslandFactors[Game.Campaign.Island]);
  DrawDialog(8, 230, 488, 320);

  if Game.World.GenerationCount < 8 then
  begin
    if Game.World.GenerationCount < 3 then
    begin
      DrawText(false, 5, 272, 'Mаксимальное количество волшебств увеличивается на 1');
      Inc(Game.Campaign.ScrollCapacity);
      Game.Runtime.LastScan := Ord(ReadKey);
    end
    else
    begin
      Game.Runtime.ActionScratch := Random(139) div 10;
      DrawText(false, 19, 272, 'Волшебство');
      DrawText(false, 30, 272, ScrollNames[shortint(Game.Runtime.ActionScratch)]);
      Inc(Game.Campaign.Scrolls[shortint(Game.Runtime.ActionScratch)]);
      Game.Runtime.LastScan := Ord(ReadKey);
    end;
  end
  else if Game.World.GenerationCount < 15 then
  begin
    Inc(Game.Campaign.Income, IslandFactors[Game.Campaign.Island] * 10);
    DrawText(false, 7, 248, 'Вы нашли алмазы и Великодушный Коpоль увеличивает');
    DrawText(false, 17, 264, 'Ваше жалование на ($):');
    Str(IslandFactors[Game.Campaign.Island] * 10, Game.Runtime.TextBuffer);
    DrawText(false, 38, 264, Game.Runtime.TextBuffer);
    PlayCue(2);
    Game.Runtime.LastScan := ReadScanCode;
  end
  else
  begin
    Game.World.GenerationCount := (Game.World.GenerationCount + TreasureGoldBases[Game.Campaign.Island]) * 10;
    Game.World.GenerationLimit := Game.World.GenerationCount div 50;
    Str(Game.World.GenerationCount, Game.Runtime.TextBuffer);
    DrawText(false, 2, 240, 'ЗОЛОТО: $');
    DrawText(false, 11, 240, Game.Runtime.TextBuffer);
    DrawText(false, 2, 256, '1) Увеличить золотой запас');
    DrawText(false, 2, 264, '2) Раздать воинам, повысив свой автоpитет на:');
    Str(Game.World.GenerationLimit, Game.Runtime.TextBuffer);
    DrawText(false, 48, 264, Game.Runtime.TextBuffer);
    Game.Runtime.CueFrequency := Game.World.GenerationCount;
    PlayCue(1);

    repeat
      Game.Runtime.LastScan := Ord(ReadKey);
      case Game.Runtime.LastScan of
        49: begin
          Game.Campaign.Gold := Game.Campaign.Gold + Game.World.GenerationCount;
          RefreshGold
        end;

        50: Game.Campaign.Leadership := Game.Campaign.Leadership + Game.World.GenerationLimit;
      end;
    until (Game.Runtime.LastScan = 49) or (Game.Runtime.LastScan = 50);
  end;
end;

procedure UndergroundVisit;
begin
  EncounterLanding;
  PlayCue(3);

  if Game.Campaign.Underground[Game.Campaign.Island, 1].X = Game.World.GenerationX then
    if Game.Campaign.Underground[Game.Campaign.Island, 1].Y = Game.World.GenerationY then
    begin
      Game.World.GenerationX := Game.Campaign.Underground[Game.Campaign.Island, 2].X + 1;
      Game.World.GenerationY := Game.Campaign.Underground[Game.Campaign.Island, 2].Y;
    end
    else
    begin
      Game.World.GenerationX := Game.Campaign.Underground[Game.Campaign.Island, 1].X + 1;
      Game.World.GenerationY := Game.Campaign.Underground[Game.Campaign.Island, 1].Y;
    end
  else
  begin
    Game.World.GenerationX := Game.Campaign.Underground[Game.Campaign.Island, 1].X + 1;
    Game.World.GenerationY := Game.Campaign.Underground[Game.Campaign.Island, 1].Y;
  end;
end;

function FindWanderingArmy(Island, X, Y: byte): shortint;
var
  I: shortint;

begin
  FindWanderingArmy := -1;
  for I := 0 to 20 do
    if (Game.Campaign.WanderingArmies[Island, I].X = X) and
      (Game.Campaign.WanderingArmies[Island, I].Y = Y) then
    begin
      FindWanderingArmy := I;
      Exit;
    end;
end;

procedure WanderingArmyVisit;
const
  ReserveMagicPower: array[0..5] of byte = (0, 2, 5, 10, 20, 35);

var
  Slot, ReserveCount: byte;
  ArmyIndex: shortint;
  Enemy: ^TWanderingArmy;
  HasTroops, ForcedBattle: boolean;

begin
  HasTroops := false;
  ReserveCount := 0;
  for Slot := 0 to 9 do
    if Game.Campaign.Army[Slot].Species < 100 then
    begin
      HasTroops := true;
      if Slot > 4 then Inc(ReserveCount);
    end;

  ArmyIndex := FindWanderingArmy(Game.Campaign.Island, Game.World.GenerationX, Game.World.GenerationY);
  if ArmyIndex < 0 then
  begin
    Game.Campaign.Map[Game.Campaign.Island, Game.World.GenerationX, Game.World.GenerationY] := 0;
    Exit;
  end;

  Enemy := @Game.Campaign.WanderingArmies[Game.Campaign.Island, ArmyIndex];
  if ArmyReport(TReportSpecies(Enemy^.Species), TReportCounts(Enemy^.Counts), ' ') then Exit;

  if Game.Campaign.MagicPower < ReserveMagicPower[ReserveCount] then
  begin
    DrawDialog(8, 230, 488, 320);
    DrawText(false, 20, 272, 'Войско неизвестно!');
  end;

  if (Game.Campaign.EnemyGrace <> 0) and not HasTroops then
  begin
    ShowNotice(9);
    Exit;
  end;

  ForcedBattle := Game.Campaign.Map[Game.Campaign.Island, Game.Campaign.Hero.X, Game.Campaign.Hero.Y] = 5;
  if ForcedBattle then
    DrawText(false, 7, 304, 'Попался! Готовься к бою ( Нажмите любую клавишу )')
  else DrawText(false, 14, 304, 'Дpаться будешь ( Y-да / N-нет ) ?');
  Game.Runtime.LastScan := ReadScanCode;
  if not ForcedBattle and (Game.Runtime.LastScan <> 21) then Exit;

  if not Game.Campaign.Flags.ArmyAvailable then
  begin
    GameOver;
    Exit;
  end;

  Battle(@Enemy^.Species, @Enemy^.Counts, 10);
  if Game.Runtime.BattleResult = 2 then DefeatReport
  else VictoryReport(ArmyIndex, 5);
  RestoreControls;
end;

procedure BoardShip;
var
  OldHeading: boolean;

begin
  Game.Campaign.Hero.X := Game.World.GenerationX;
  Game.Campaign.Hero.Y := Game.World.GenerationY;
  Game.Runtime.ShipAbandonBlocked := true;
  AbandonShip;
  Game.Campaign.Flags.ShipOwned := true;
  OldHeading := Game.Campaign.Flags.Heading;
  Game.Campaign.Flags.Heading := boolean(Game.Campaign.ShipHeading);
  Game.Campaign.ShipHeading := Ord(OldHeading);
end;

procedure SandLanding;
begin
  EncounterLanding;
  if Game.Campaign.ExtraDays > 0 then
  begin
    Game.Campaign.ExtraDays := 0;
    DrawTime
  end
  else if Game.Campaign.Days > 29 then Dec(Game.Campaign.Days, 29)
  else Game.Campaign.Days := 1;
end;

procedure RitualGuardianVisit;
var
  UnknownLocal: byte;
  Text: string[30];

begin
  if ArmyReport(TReportSpecies(Game.Campaign.GuardianSpecies), TReportCounts(Game.Campaign.GuardianCounts), ' ') then;
  DrawText(false, 14, 304, 'Дpаться будешь ( Y-да / N-нет ) ?');
  Game.Runtime.LastScan := ReadScanCode;

  if Game.Runtime.LastScan = 21 then
    if Game.Campaign.Flags.ArmyAvailable then
    begin
      Battle(@Game.Campaign.GuardianSpecies, @Game.Campaign.GuardianCounts, 8);

      if Game.Runtime.BattleResult = 2 then
      begin
        Game.Campaign.Map[Game.Campaign.Island, Game.World.GenerationX, Game.World.GenerationY] := 0;
        Game.Campaign.HiddenSpellIsland := 100;
      end
      else
      begin
        DrawDialog(8, 230, 584, 320);
        Text := 'Вы нашли ' + Game.Runtime.SpellTitles[Game.Campaign.HiddenSpellEffect] + ' заклинание.';
        DrawText(false, 13, 264, Text);
        Game.Campaign.Map[Game.Campaign.Island, Game.World.GenerationX, Game.World.GenerationY] := 0;
        Game.Campaign.Flags.SpellAvailable[Game.Campaign.HiddenSpellEffect] := true;
        Game.Campaign.HiddenSpellIsland := 100;

        if CountRitualSpells = 1 then Game.Campaign.Flags.InstructionsShown := false;
        Game.Runtime.LastScan := ReadScanCode;
      end;

      RestoreControls;
    end
    else
    begin
      Game.Campaign.Map[Game.Campaign.Island, Game.World.GenerationX, Game.World.GenerationY] := 0;
      Game.Campaign.HiddenSpellIsland := 100;
    end;
end;

procedure RegrowMountain;
var
  Slot: shortint;

begin
  Dec(Game.Runtime.RegrowthCountdown);
  if Game.Runtime.RegrowthCountdown = 0 then
    if (Game.Runtime.RegrowthPosition.X = Game.World.GenerationX)
      and (Game.Runtime.RegrowthPosition.Y = Game.World.GenerationY) then Inc(Game.Runtime.RegrowthCountdown)
    else
    begin
      if Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y] = 14 then AbandonShip;

      if Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y] = 5 then
      begin
        Slot := FindWanderingArmy(5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y);
        if Slot >= 0 then Game.Campaign.WanderingArmies[5, Slot].X := 255;
      end;

      Game.Runtime.ShoreTile := 80;
      if (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y - 1] > 79)
        and (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y - 1] < 96) then
      begin
        Inc(Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y - 1], 2);
        Inc(Game.Runtime.ShoreTile, 1);
      end;

      if (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y + 1] > 79)
        and (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y + 1] < 96) then
      begin
        Inc(Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y + 1], 1);
        Inc(Game.Runtime.ShoreTile, 2);
      end;

      if (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X - 1, Game.Runtime.RegrowthPosition.Y] > 79)
        and (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X - 1, Game.Runtime.RegrowthPosition.Y] < 96) then
      begin
        Inc(Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X - 1, Game.Runtime.RegrowthPosition.Y], 8);
        Inc(Game.Runtime.ShoreTile, 4);
      end;

      if (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X + 1, Game.Runtime.RegrowthPosition.Y] > 79)
        and (Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X + 1, Game.Runtime.RegrowthPosition.Y] < 96) then
      begin
        Inc(Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X + 1, Game.Runtime.RegrowthPosition.Y], 4);
        Inc(Game.Runtime.ShoreTile, 8);
      end;

      Game.Campaign.Map[5, Game.Runtime.RegrowthPosition.X, Game.Runtime.RegrowthPosition.Y] :=
    Game.Runtime.ShoreTile;
      Game.Runtime.RegrowthPosition.X := 100;
    end;
end;
end.
