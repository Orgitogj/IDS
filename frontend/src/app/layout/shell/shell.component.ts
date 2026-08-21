import {Component} from '@angular/core';
import {RouterLink,RouterLinkActive,RouterOutlet} from '@angular/router';
@Component({
  selector:'app-shell',
  standalone:true,
  imports:[RouterLink,RouterLinkActive,RouterOutlet],
  templateUrl:'shell.component.html',
  styleUrl:'shell.component.css'
})
export class ShellComponent{}
